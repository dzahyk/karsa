"""Database-level immutability (defence in depth for audit-sensitive tables).

* audit_events and approval_records: no UPDATE, no DELETE.
* decision_packages: content and content_hash can never change once inserted (state may change).
"""

from __future__ import annotations

SQLITE = [
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS approval_records_no_update BEFORE UPDATE ON approval_records
       BEGIN SELECT RAISE(ABORT, 'approval_records are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS approval_records_no_delete BEFORE DELETE ON approval_records
       BEGIN SELECT RAISE(ABORT, 'approval_records are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS packages_content_frozen BEFORE UPDATE OF content, content_hash ON decision_packages
       WHEN NEW.content IS NOT OLD.content OR NEW.content_hash IS NOT OLD.content_hash
       BEGIN SELECT RAISE(ABORT, 'decision package content is frozen'); END""",
]

POSTGRES = [
    """CREATE OR REPLACE FUNCTION df_forbid() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION '% is immutable', TG_TABLE_NAME; END; $$ LANGUAGE plpgsql""",
    "CREATE TRIGGER audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION df_forbid()",
    "CREATE TRIGGER approval_records_immutable BEFORE UPDATE OR DELETE ON approval_records "
    "FOR EACH ROW EXECUTE FUNCTION df_forbid()",
    """CREATE OR REPLACE FUNCTION df_package_frozen() RETURNS trigger AS $$
       BEGIN IF NEW.content::text <> OLD.content::text OR NEW.content_hash <> OLD.content_hash
       THEN RAISE EXCEPTION 'decision package content is frozen'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""",
    "CREATE TRIGGER packages_content_frozen BEFORE UPDATE ON decision_packages FOR EACH ROW "
    "EXECUTE FUNCTION df_package_frozen()",
]


def install(conn) -> None:
    stmts = SQLITE if conn.dialect.name == "sqlite" else POSTGRES
    for sql in stmts:
        conn.exec_driver_sql(sql)
