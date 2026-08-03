"""add simple account ownership and credentials

Revision ID: 8f4b2c6d3e51
Revises: 6c1a5e9b2d34
Create Date: 2026-08-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f4b2c6d3e51"
down_revision: str | None = "6c1a5e9b2d34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_cols = {item["name"] for item in inspector.get_columns("app_users")}
    if "password_hash" not in user_cols:
        op.add_column("app_users", sa.Column("password_hash", sa.String(length=256), nullable=True))
    candidate_cols = {item["name"] for item in inspector.get_columns("candidates")}
    if "owner_user_id" not in candidate_cols:
        op.add_column("candidates", sa.Column("owner_user_id", sa.BigInteger(), nullable=True))
        op.create_index("ix_candidates_owner_user_id", "candidates", ["owner_user_id"], unique=False)
        op.create_foreign_key("fk_candidates_owner_user", "candidates", "app_users", ["owner_user_id"], ["id"])
    claim_cols = {item["name"] for item in inspector.get_columns("candidate_identity_claims")}
    if "owner_user_id" not in claim_cols:
        op.add_column("candidate_identity_claims", sa.Column("owner_user_id", sa.BigInteger(), nullable=True))
        op.create_index("ix_candidate_claims_owner_user_id", "candidate_identity_claims", ["owner_user_id"], unique=False)
        op.create_foreign_key("fk_candidate_claims_owner_user", "candidate_identity_claims", "app_users", ["owner_user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_candidate_claims_owner_user", "candidate_identity_claims", type_="foreignkey")
    op.drop_index("ix_candidate_claims_owner_user_id", table_name="candidate_identity_claims")
    op.drop_column("candidate_identity_claims", "owner_user_id")
    op.drop_constraint("fk_candidates_owner_user", "candidates", type_="foreignkey")
    op.drop_index("ix_candidates_owner_user_id", table_name="candidates")
    op.drop_column("candidates", "owner_user_id")
    op.drop_column("app_users", "password_hash")
