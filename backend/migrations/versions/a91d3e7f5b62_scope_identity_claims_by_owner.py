"""scope candidate identity claims by account owner

Revision ID: a91d3e7f5b62
Revises: 8f4b2c6d3e51
Create Date: 2026-08-03
"""

from collections.abc import Sequence  # noqa: I001

from alembic import op


revision: str = "a91d3e7f5b62"
down_revision: str | None = "8f4b2c6d3e51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The original unique key was also selected by InnoDB to support the
    # organization foreign key. Keep an independent leading-column index
    # before replacing that key.
    op.create_index(
        "ix_candidate_identity_claim_organization",
        "candidate_identity_claims",
        ["organization_id"],
        unique=False,
    )
    op.drop_constraint("uq_candidate_identity_claim", "candidate_identity_claims", type_="unique")
    op.create_unique_constraint(
        "uq_candidate_identity_claim",
        "candidate_identity_claims",
        ["organization_id", "owner_user_id", "identity_type", "identity_hash"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_candidate_identity_claim", "candidate_identity_claims", type_="unique")
    op.create_unique_constraint(
        "uq_candidate_identity_claim",
        "candidate_identity_claims",
        ["organization_id", "identity_type", "identity_hash"],
    )
    op.drop_index("ix_candidate_identity_claim_organization", table_name="candidate_identity_claims")
