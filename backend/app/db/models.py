from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class User(Base, TimestampMixin):
    __tablename__ = "app_users"
    __table_args__ = (UniqueConstraint("organization_id", "email_hash"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email_ciphertext: Mapped[str] = mapped_column(Text)
    email_hash: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    password_hash: Mapped[str | None] = mapped_column(String(256))


class JobPosition(Base, TimestampMixin):
    __tablename__ = "job_positions"
    __table_args__ = (Index("ix_job_org_status_updated", "organization_id", "status", "updated_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(200))
    jd_content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    active_requirement_version_id: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)


class JobRequirementVersion(Base):
    __tablename__ = "job_requirement_versions"
    __table_args__ = (UniqueConstraint("job_id", "version_no"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_positions.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    rubric_version: Mapped[str] = mapped_column(String(50))
    weight_config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    published_at: Mapped[datetime | None] = mapped_column(DateTime)


class RequirementItem(Base):
    __tablename__ = "requirement_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    requirement_version_id: Mapped[int] = mapped_column(
        ForeignKey("job_requirement_versions.id"), index=True
    )
    dimension_code: Mapped[str] = mapped_column(String(50))
    item_code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    requirement_type: Mapped[str] = mapped_column(String(32))
    max_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    is_gate: Mapped[bool] = mapped_column(Boolean, default=False)
    acceptable_alternatives: Mapped[list | None] = mapped_column(JSON)
    evidence_rule: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"
    __table_args__ = (
        Index("ix_candidate_org_email_hash", "organization_id", "email_hash"),
        Index("ix_candidate_org_phone_hash", "organization_id", "phone_hash"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"), index=True)
    name_ciphertext: Mapped[str | None] = mapped_column(Text)
    name_hash: Mapped[str | None] = mapped_column(String(64))
    email_ciphertext: Mapped[str | None] = mapped_column(Text)
    email_hash: Mapped[str | None] = mapped_column(String(64))
    phone_ciphertext: Mapped[str | None] = mapped_column(Text)
    phone_hash: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(100))
    consent_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class CandidateIdentityClaim(Base):
    """One canonical owner for each organization-scoped deduplication identity."""

    __tablename__ = "candidate_identity_claims"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "owner_user_id",
            "identity_type",
            "identity_hash",
            name="uq_candidate_identity_claim",
        ),
        Index("ix_candidate_identity_claim_candidate", "candidate_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"), index=True)
    identity_type: Mapped[str] = mapped_column(String(16))
    identity_hash: Mapped[str] = mapped_column(String(64))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ResumeFile(Base):
    __tablename__ = "resume_files"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    malware_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    preparsed_text_storage_key: Mapped[str | None] = mapped_column(String(500))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class ResumeParseVersion(Base):
    __tablename__ = "resume_parse_versions"
    __table_args__ = (UniqueConstraint("resume_file_id", "version_no"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resume_file_id: Mapped[int] = mapped_column(ForeignKey("resume_files.id"))
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    parser_version: Mapped[str] = mapped_column(String(50))
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    normalized_text_storage_key: Mapped[str | None] = mapped_column(String(500))
    profile_json: Mapped[dict | None] = mapped_column(JSON)
    validation_errors: Mapped[list | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class JobApplication(Base, TimestampMixin):
    __tablename__ = "job_applications"
    __table_args__ = (Index("ix_application_job_stage_created", "job_id", "stage", "created_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_positions.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    resume_file_id: Mapped[int] = mapped_column(ForeignKey("resume_files.id"))
    stage: Mapped[str] = mapped_column(String(32), default="APPLIED")
    source: Mapped[str | None] = mapped_column(String(100))


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"
    __table_args__ = (
        Index("ix_task_claim", "status", "available_at", "priority"),
        Index("ix_task_org_created", "organization_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    task_type: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    available_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    locked_by: Mapped[str | None] = mapped_column(String(100))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message_safe: Mapped[str | None] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class CandidateEvaluation(Base):
    __tablename__ = "candidate_evaluations"
    __table_args__ = (Index("ix_evaluation_application_created", "application_id", "created_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id"))
    parse_version_id: Mapped[int] = mapped_column(ForeignKey("resume_parse_versions.id"))
    requirement_version_id: Mapped[int] = mapped_column(ForeignKey("job_requirement_versions.id"))
    status: Mapped[str] = mapped_column(String(32))
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    level: Mapped[str | None] = mapped_column(String(32))
    gate_result: Mapped[str | None] = mapped_column(String(32))
    summary_json: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    rubric_version: Mapped[str] = mapped_column(String(50))
    prompt_version: Mapped[str] = mapped_column(String(50))
    model_provider: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(100))
    supersedes_evaluation_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_evaluations.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class EvaluationScoreDetail(Base):
    __tablename__ = "evaluation_score_details"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("candidate_evaluations.id"), index=True)
    dimension_code: Mapped[str] = mapped_column(String(50))
    item_code: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32))
    depth: Mapped[str | None] = mapped_column(String(16), nullable=True)
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    max_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    reason: Mapped[str] = mapped_column(Text)
    calculation_json: Mapped[dict | None] = mapped_column(JSON)


class EvaluationEvidence(Base):
    __tablename__ = "evaluation_evidences"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    score_detail_id: Mapped[int] = mapped_column(ForeignKey("evaluation_score_details.id"))
    parse_version_id: Mapped[int] = mapped_column(ForeignKey("resume_parse_versions.id"))
    page_no: Mapped[int] = mapped_column(Integer)
    block_id: Mapped[str | None] = mapped_column(String(100))
    quote_text: Mapped[str] = mapped_column(Text)
    bbox_json: Mapped[dict | None] = mapped_column(JSON)
    evidence_type: Mapped[str] = mapped_column(String(32), default="DIRECT")


class HumanDecision(Base):
    __tablename__ = "human_decisions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("candidate_evaluations.id"))
    decision: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class InterviewFeedback(Base):
    __tablename__ = "interview_feedback"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id"))
    round_name: Mapped[str] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(32))
    dimension_feedback: Mapped[dict | None] = mapped_column(JSON)
    comment: Mapped[str | None] = mapped_column(Text)
    interviewer_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
