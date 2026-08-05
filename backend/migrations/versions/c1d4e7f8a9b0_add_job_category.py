"""add job category

Revision ID: c1d4e7f8a9b0
Revises: a91d3e7f5b62
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa


revision: str = "c1d4e7f8a9b0"
down_revision: str | None = "a91d3e7f5b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_positions",
        sa.Column("job_category", sa.String(length=50), nullable=False, server_default="GENERAL"),
    )
    op.alter_column("job_positions", "job_category", server_default=None)


def downgrade() -> None:
    op.drop_column("job_positions", "job_category")
