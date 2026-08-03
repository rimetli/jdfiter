"""add concurrency-safe candidate identity claims

Revision ID: 6c1a5e9b2d34
Revises: 3e7a4c8d1f12
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c1a5e9b2d34"
down_revision: str | None = "3e7a4c8d1f12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "candidate_identity_claims" in inspector.get_table_names():
        return
    op.create_table(
        "candidate_identity_claims",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column("identity_type", sa.String(length=16), nullable=False),
        sa.Column("identity_hash", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "identity_type", "identity_hash", name="uq_candidate_identity_claim"
        ),
    )
    op.create_index(
        "ix_candidate_identity_claim_candidate",
        "candidate_identity_claims",
        ["candidate_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_identity_claim_candidate", table_name="candidate_identity_claims")
    op.drop_table("candidate_identity_claims")
