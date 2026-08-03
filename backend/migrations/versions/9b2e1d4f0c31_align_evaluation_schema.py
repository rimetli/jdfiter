"""align evaluation schema with application models

Revision ID: 9b2e1d4f0c31
Revises: 7222483c812c
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b2e1d4f0c31"
down_revision: str | None = "7222483c812c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Some early local deployments added these fields by hand before Alembic was
    # introduced. Inspect first so upgrading such a database remains safe.
    inspector = sa.inspect(op.get_bind())
    score_columns = {
        column["name"] for column in inspector.get_columns("evaluation_score_details")
    }
    if "depth" not in score_columns:
        op.add_column(
            "evaluation_score_details",
            sa.Column("depth", sa.String(length=16), nullable=True),
        )
    if "role" not in score_columns:
        op.add_column(
            "evaluation_score_details",
            sa.Column("role", sa.String(length=16), nullable=True),
        )

    decision_columns = {
        column["name"]: column for column in inspector.get_columns("human_decisions")
    }
    if not decision_columns["decided_by"]["nullable"]:
        op.alter_column(
            "human_decisions",
            "decided_by",
            existing_type=sa.BigInteger(),
            nullable=True,
        )


def downgrade() -> None:
    op.alter_column(
        "human_decisions",
        "decided_by",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.drop_column("evaluation_score_details", "role")
    op.drop_column("evaluation_score_details", "depth")
