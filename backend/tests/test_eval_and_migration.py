import sqlite3
import subprocess
import sys
from pathlib import Path

from app.domain.hashing import content_hash
from app.evaluation.dataset import CASES
from app.models import EvalCase, EvalDataset


def test_eval_run_scores_all_cases_and_reports_real_failures(api, db):
    s = db()
    ds = EvalDataset(slug="b", name="b", version="v1.0", description="d", manifest_hash=content_hash({"c": CASES}))
    s.add(ds)
    s.flush()
    for c in CASES:
        s.add(EvalCase(dataset_id=ds.id, code=c["code"], category=c["category"], brief=c["brief"],
                       expected=c["expected"]))
    s.commit()
    r = api.post("/evaluations/runs", {"dataset_id": ds.id}, user="u_priya")
    assert r.status_code == 201
    summary = r.json()["summary"]
    assert summary["cases"] == 24
    assert summary["calculation_exact"] == 24  # deterministic engine matches hand-computed oracles
    assert summary["grounding_rate"] == 1.0
    assert set(summary["splits"]) == {"dev"} and summary["gate"]["applied_to"] == "all"
    lo, hi = summary["pass_rate_ci95"]
    assert lo <= summary["pass_rate"] <= hi


def test_alembic_migration_builds_schema(tmp_path):
    db_file = tmp_path / "m.db"
    root = Path(__file__).resolve().parents[1]
    env = {"DATABASE_URL": f"sqlite:///{db_file}", "PATH": "/usr/bin:/bin"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env, check=True,
                   capture_output=True)
    tables = {r[0] for r in sqlite3.connect(db_file).execute("select name from sqlite_master where type='table'")}
    assert {"cases", "decision_packages", "approval_records", "sandbox_records", "audit_events", "outbox_events",
            "incidents", "auth_sessions", "organizations"} <= tables
    triggers = {r[0] for r in sqlite3.connect(db_file).execute("select name from sqlite_master where type='trigger'")}
    assert {"audit_events_no_update", "audit_events_no_delete", "packages_content_frozen"} <= triggers
