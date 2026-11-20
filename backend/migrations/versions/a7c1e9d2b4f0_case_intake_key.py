"""case intake idempotency key

Revision ID: a7c1e9d2b4f0
Revises: 312e45f18170
Create Date: 2026-11-21 10:00:00

A case created by an automated intake (the n8n workflow) carries the caller's Idempotency-Key, unique per
organisation, so a replayed delivery returns the existing case instead of creating a duplicate.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c1e9d2b4f0"
down_revision: Union[str, Sequence[str], None] = "312e45f18170"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("cases") as batch:
        batch.add_column(sa.Column("intake_key", sa.String(length=120), nullable=True))
        batch.create_unique_constraint("uq_cases_org_intake_key", ["organization_id", "intake_key"])


def downgrade() -> None:
    with op.batch_alter_table("cases") as batch:
        batch.drop_constraint("uq_cases_org_intake_key", type_="unique")
        batch.drop_column("intake_key")
