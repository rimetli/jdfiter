import hashlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.jobs import get_job_or_404
from app.core.auth import get_current_user
from app.db.models import (
    CandidateEvaluation,
    HumanDecision,
    JobApplication,
    ProcessingTask,
    ResumeFile,
    ResumeParseVersion,
    User,
)
from app.db.session import get_db

router = APIRouter(prefix="/jobs", tags=["candidates"])


class BatchAnalyzeRequest(BaseModel):
    application_ids: list[int] = Field(min_length=1, max_length=5)
    confirm_reevaluate: bool = False


@router.get("/{job_id}/candidates")
async def list_candidates(
    job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    await get_job_or_404(job_id, db, user)
    applications = list(
        await db.scalars(
            select(JobApplication)
            .where(JobApplication.job_id == job_id)
            .order_by(JobApplication.created_at.desc())
        )
    )
    result = []
    for application in applications:
        resume = await db.get(ResumeFile, application.resume_file_id)
        parse = await db.scalar(
            select(ResumeParseVersion)
            .where(ResumeParseVersion.resume_file_id == application.resume_file_id)
            .order_by(ResumeParseVersion.version_no.desc()).limit(1)
        )
        evaluation = await db.scalar(
            select(CandidateEvaluation)
            .where(CandidateEvaluation.application_id == application.id)
            .order_by(CandidateEvaluation.created_at.desc()).limit(1)
        )
        latest_analysis_task = await db.scalar(
            select(ProcessingTask)
            .where(
                ProcessingTask.task_type == "ANALYZE_APPLICATION",
                ProcessingTask.entity_id == application.id,
            ).order_by(ProcessingTask.created_at.desc()).limit(1)
        )
        parse_task = await db.scalar(
            select(ProcessingTask)
            .where(
                ProcessingTask.task_type == "PARSE_RESUME",
                ProcessingTask.entity_type == "RESUME_FILE",
                ProcessingTask.entity_id == application.resume_file_id,
            ).order_by(ProcessingTask.created_at.desc()).limit(1)
        )
        decision = None
        if evaluation is not None:
            decision = await db.scalar(
                select(HumanDecision)
                .where(HumanDecision.evaluation_id == evaluation.id)
                .order_by(HumanDecision.created_at.desc(), HumanDecision.id.desc())
                .limit(1)
            )
        result.append({
            "application_id": application.id,
            "filename": resume.original_filename if resume else "unknown.pdf",
            "parse_status": parse.status if parse else "PENDING",
            "parse_task_id": parse_task.id if parse_task else None,
            "analysis_task_id": latest_analysis_task.id if latest_analysis_task else None,
            "analysis_status": latest_analysis_task.status if latest_analysis_task else (evaluation.status if evaluation else "NOT_ANALYZED"),
            "analysis_progress": latest_analysis_task.progress if latest_analysis_task else (100 if evaluation else 0),
            "analysis_error": latest_analysis_task.error_message_safe if latest_analysis_task else None,
            "evaluation_id": evaluation.id if evaluation else None,
            "score": float(evaluation.total_score) if evaluation and evaluation.total_score is not None else None,
            "level": evaluation.level if evaluation else None,
            "gate_result": evaluation.gate_result if evaluation else None,
            "decision": decision.decision if decision else None,
            "uploaded_at": application.created_at,
        })
    return result


@router.post("/{job_id}/evaluations/batch", status_code=202)
async def batch_analyze(
    job_id: int,
    payload: BatchAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    job = await get_job_or_404(job_id, db, user)
    if job.status != "ACTIVE" or job.active_requirement_version_id is None:
        raise HTTPException(status_code=409, detail="请先发布能力模型")
    created, skipped = [], []
    for application_id in dict.fromkeys(payload.application_ids):
        application = await db.get(JobApplication, application_id)
        if application is None or application.job_id != job_id:
            skipped.append({"application_id": application_id, "reason": "申请不存在"})
            continue
        parse = await db.scalar(
            select(ResumeParseVersion)
            .where(
                ResumeParseVersion.resume_file_id == application.resume_file_id,
                ResumeParseVersion.status == "COMPLETED",
            ).order_by(ResumeParseVersion.version_no.desc()).limit(1)
        )
        if parse is None:
            skipped.append({"application_id": application_id, "reason": "简历未解析完成"})
            continue
        existing = await db.scalar(
            select(ProcessingTask).where(
                ProcessingTask.task_type == "ANALYZE_APPLICATION",
                ProcessingTask.entity_id == application_id,
                ProcessingTask.status.in_(["PENDING", "PROCESSING"]),
            ).limit(1)
        )
        if existing:
            skipped.append({"application_id": application_id, "reason": "分析任务已存在"})
            continue
        prior_evaluation = await db.scalar(
            select(CandidateEvaluation)
            .where(CandidateEvaluation.application_id == application_id)
            .limit(1)
        )
        if prior_evaluation is not None and not payload.confirm_reevaluate:
            skipped.append({"application_id": application_id, "reason": "已有评估结果，需确认重评"})
            continue
        fingerprint = f"{application_id}:{parse.id}:{job.active_requirement_version_id}".encode()
        task = ProcessingTask(
            organization_id=job.organization_id,
            task_type="ANALYZE_APPLICATION",
            entity_type="JOB_APPLICATION",
            entity_id=application_id,
            status="PENDING",
            progress=0,
            input_hash=hashlib.sha256(fingerprint).hexdigest(),
        )
        db.add(task)
        await db.flush()
        created.append({"application_id": application_id, "task_id": task.id})
    await db.commit()
    return {"created": created, "skipped": skipped}
