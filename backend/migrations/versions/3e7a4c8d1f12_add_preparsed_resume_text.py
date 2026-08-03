"""store upload-time vision OCR text

Revision ID: 3e7a4c8d1f12
Revises: 9b2e1d4f0c31
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e7a4c8d1f12"
down_revision: str | None = "9b2e1d4f0c31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("resume_files")}
    if "preparsed_text_storage_key" not in columns:
        op.add_column(
            "resume_files",
            sa.Column("preparsed_text_storage_key", sa.String(length=500), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("resume_files", "preparsed_text_storage_key")
