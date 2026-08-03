from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.jobs import get_job_or_404
from app.core.auth import get_current_user
from app.db.models import (
    CandidateEvaluation,
    EvaluationEvidence,
    EvaluationScoreDetail,
    HumanDecision,
    JobApplication,
    JobRequirementVersion,
    ResumeFile,
    User,
)
from app.db.session import get_db

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

VALID_DECISIONS = {"ADVANCE", "REJECT", "HOLD"}


class HumanDecisionCreate(BaseModel):
    decision: str
    reason_code: str = Field(default="MANUAL", max_length=100)
    comment: str | None = None


async def _latest_decision(db: AsyncSession, evaluation_id: int) -> HumanDecision | None:
    return await db.scalar(
        select(HumanDecision)
        .where(HumanDecision.evaluation_id == evaluation_id)
        .order_by(HumanDecision.created_at.desc(), HumanDecision.id.desc())
        .limit(1)
    )


def _serialize_decision(decision: HumanDecision | None) -> dict | None:
    if decision is None:
        return None
    return {
        "decision": decision.decision,
        "reason_code": decision.reason_code,
        "comment": decision.comment,
        "created_at": decision.created_at,
    }


async def _get_evaluation_for_user(
    evaluation_id: int, db: AsyncSession, user: User
) -> CandidateEvaluation:
    evaluation = await db.get(CandidateEvaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="评估结果不存在")
    application = await db.get(JobApplication, evaluation.application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="评估结果不存在")
    await get_job_or_404(application.job_id, db, user)
    return evaluation


@router.get("/{evaluation_id}")
async def get_evaluation(
    evaluation_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    evaluation = await _get_evaluation_for_user(evaluation_id, db, user)
    details = list(
        await db.scalars(
            select(EvaluationScoreDetail)
            .where(EvaluationScoreDetail.evaluation_id == evaluation_id)
            .order_by(EvaluationScoreDetail.id)
        )
    )
    output_details = []
    for detail in details:
        evidences = list(
            await db.scalars(
                select(EvaluationEvidence).where(EvaluationEvidence.score_detail_id == detail.id)
            )
        )
        output_details.append({
            "id": detail.id,
            "dimension_code": detail.dimension_code,
            "status": detail.status,
            "depth": detail.depth,
            "role": detail.role,
            "score": float(detail.score),
            "max_score": float(detail.max_score),
            "confidence": float(detail.confidence),
            "reason": detail.reason,
            "evidence": [
                {"page_no": item.page_no, "quote": item.quote_text} for item in evidences
            ],
        })

    filename = None
    application = await db.get(JobApplication, evaluation.application_id)
    if application is not None:
        resume = await db.get(ResumeFile, application.resume_file_id)
        filename = resume.original_filename if resume else None
    requirement_version = await db.get(
        JobRequirementVersion, evaluation.requirement_version_id
    )
    decision = await _latest_decision(db, evaluation_id)

    return {
        "id": evaluation.id,
        "application_id": evaluation.application_id,
        "filename": filename,
        "score": float(evaluation.total_score or 0),
        "level": evaluation.level,
        "gate_result": evaluation.gate_result,
        "confidence": float(evaluation.confidence or 0),
        "summary": evaluation.summary_json or {},
        "details": output_details,
        "model": evaluation.model_name,
        "prompt_version": evaluation.prompt_version,
        "rubric_version": evaluation.rubric_version,
        "requirement_version_no": (
            requirement_version.version_no if requirement_version else None
        ),
        "human_decision": _serialize_decision(decision),
        "created_at": evaluation.created_at,
    }


@router.post("/{evaluation_id}/human-decision", status_code=status.HTTP_201_CREATED)
async def create_human_decision(
    evaluation_id: int,
    payload: HumanDecisionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    await _get_evaluation_for_user(evaluation_id, db, user)
    decision_value = payload.decision.strip().upper()
    if decision_value not in VALID_DECISIONS:
        raise HTTPException(status_code=422, detail="无效的决策类型")
    record = HumanDecision(
        evaluation_id=evaluation_id,
        decision=decision_value,
        reason_code=payload.reason_code or "MANUAL",
        comment=payload.comment,
        decided_by=user.id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _serialize_decision(record)
