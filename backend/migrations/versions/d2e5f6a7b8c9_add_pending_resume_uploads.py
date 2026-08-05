"""add pending resume uploads

Revision ID: d2e5f6a7b8c9
Revises: c1d4e7f8a9b0
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa


revision: str = "d2e5f6a7b8c9"
down_revision: str | None = "c1d4e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_resume_uploads",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.BigInteger(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("job_id", sa.BigInteger(), sa.ForeignKey("job_positions.id"), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.BigInteger(), sa.ForeignKey("app_users.id")),
        sa.Column("resume_file_id", sa.BigInteger(), sa.ForeignKey("resume_files.id")),
        sa.Column("application_id", sa.BigInteger(), sa.ForeignKey("job_applications.id")),
        sa.Column("duplicate", sa.Boolean()),
        sa.Column("match_rule", sa.String(length=16)),
        sa.Column("result_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_pending_resume_job_owner", "pending_resume_uploads", ["job_id", "uploaded_by", "created_at"])
    op.create_index("ix_pending_resume_uploads_job_id", "pending_resume_uploads", ["job_id"])
    op.create_index("ix_pending_resume_uploads_sha256", "pending_resume_uploads", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_pending_resume_uploads_sha256", table_name="pending_resume_uploads")
    op.drop_index("ix_pending_resume_uploads_job_id", table_name="pending_resume_uploads")
    op.drop_index("ix_pending_resume_job_owner", table_name="pending_resume_uploads")
    op.drop_table("pending_resume_uploads")
