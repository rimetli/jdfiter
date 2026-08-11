import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.jobs import get_job_or_404
from app.core.auth import get_current_user
from app.db.models import (
    Candidate,
    CandidateEvaluation,
    HumanDecision,
    InterviewFeedback,
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


class InterviewFeedbackCreate(BaseModel):
    round_name: str = Field(min_length=1, max_length=100)
    result: str = Field(min_length=1, max_length=32)
    dimension_feedback: dict[str, str] | None = None
    comment: str | None = Field(default=None, max_length=5000)


VALID_INTERVIEW_RESULTS = {"ADVANCE", "HOLD", "REJECT"}


def _serialize_interview_feedback(feedback: InterviewFeedback, interviewer_name: str | None) -> dict:
    return {
        "id": feedback.id,
        "round_name": feedback.round_name,
        "result": feedback.result,
        "dimension_feedback": feedback.dimension_feedback or {},
        "comment": feedback.comment,
        "interviewer_name": interviewer_name or "未知用户",
        "created_at": feedback.created_at,
    }


@router.get("/{job_id}/candidates")
async def list_candidates(
    job_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    gate_result: str | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=100),
    parse_status: str | None = Query(default=None, max_length=32),
    analysis_status: str | None = Query(default=None, max_length=32),
    decision: str | None = Query(default=None, max_length=32),
    has_interview_feedback: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    await get_job_or_404(job_id, db, user)
    application_statement = select(JobApplication).where(JobApplication.job_id == job_id)
    if gate_result:
        application_statement = application_statement.join(
            CandidateEvaluation,
            CandidateEvaluation.application_id == JobApplication.id,
        ).where(CandidateEvaluation.gate_result == gate_result).distinct()
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip().lower()}%"
        application_statement = application_statement.join(
            ResumeFile, ResumeFile.id == JobApplication.resume_file_id
        ).outerjoin(Candidate, Candidate.id == JobApplication.candidate_id).where(
            or_(
                func.lower(ResumeFile.original_filename).like(pattern),
                func.lower(func.coalesce(Candidate.name_ciphertext, "")).like(pattern),
            )
        )
    latest_parse_status = (
        select(ResumeParseVersion.status)
        .where(ResumeParseVersion.resume_file_id == JobApplication.resume_file_id)
        .order_by(ResumeParseVersion.version_no.desc())
        .limit(1)
        .scalar_subquery()
    )
    latest_evaluation_id = (
        select(CandidateEvaluation.id)
        .where(CandidateEvaluation.application_id == JobApplication.id)
        .order_by(CandidateEvaluation.created_at.desc(), CandidateEvaluation.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    latest_evaluation_status = (
        select(CandidateEvaluation.status)
        .where(CandidateEvaluation.id == latest_evaluation_id)
        .scalar_subquery()
    )
    latest_analysis_status = (
        select(ProcessingTask.status)
        .where(
            ProcessingTask.task_type == "ANALYZE_APPLICATION",
            ProcessingTask.entity_id == JobApplication.id,
        )
        .order_by(ProcessingTask.created_at.desc(), ProcessingTask.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    latest_decision = (
        select(HumanDecision.decision)
        .where(HumanDecision.evaluation_id == latest_evaluation_id)
        .order_by(HumanDecision.created_at.desc(), HumanDecision.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    feedback_exists = exists(
        select(InterviewFeedback.id).where(InterviewFeedback.application_id == JobApplication.id)
    )
    if parse_status:
        application_statement = application_statement.where(
            func.coalesce(latest_parse_status, "PENDING") == parse_status
        )
    if analysis_status:
        application_statement = application_statement.where(
            func.coalesce(latest_analysis_status, latest_evaluation_status, "NOT_ANALYZED")
            == analysis_status
        )
    if decision:
        application_statement = application_statement.where(latest_decision == decision)
    if has_interview_feedback is True:
        application_statement = application_statement.where(feedback_exists)
    elif has_interview_feedback is False:
        application_statement = application_statement.where(not_(feedback_exists))
    total = await db.scalar(select(func.count()).select_from(application_statement.subquery())) or 0
    applications = list(await db.scalars(
        application_statement.order_by(JobApplication.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ))
    application_ids = [application.id for application in applications]
    resume_ids = [application.resume_file_id for application in applications]
    resumes = {
        resume.id: resume
        for resume in await db.scalars(select(ResumeFile).where(ResumeFile.id.in_(resume_ids)))
    } if resume_ids else {}
    candidate_ids = [application.candidate_id for application in applications]
    candidates = {
        candidate.id: candidate
        for candidate in await db.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids)))
    } if candidate_ids else {}
    parses: dict[int, ResumeParseVersion] = {}
    if resume_ids:
        for parse in await db.scalars(
            select(ResumeParseVersion)
            .where(ResumeParseVersion.resume_file_id.in_(resume_ids))
            .order_by(ResumeParseVersion.resume_file_id, ResumeParseVersion.version_no.desc())
        ):
            parses.setdefault(parse.resume_file_id, parse)
    evaluations: dict[int, CandidateEvaluation] = {}
    if application_ids:
        for evaluation in await db.scalars(
            select(CandidateEvaluation)
            .where(CandidateEvaluation.application_id.in_(application_ids))
            .order_by(CandidateEvaluation.application_id, CandidateEvaluation.created_at.desc(), CandidateEvaluation.id.desc())
        ):
            evaluations.setdefault(evaluation.application_id, evaluation)
    analysis_tasks: dict[int, ProcessingTask] = {}
    parse_tasks: dict[int, ProcessingTask] = {}
    if application_ids:
        for task in await db.scalars(
            select(ProcessingTask)
            .where(
                ProcessingTask.task_type == "ANALYZE_APPLICATION",
                ProcessingTask.entity_id.in_(application_ids),
            )
            .order_by(ProcessingTask.entity_id, ProcessingTask.created_at.desc(), ProcessingTask.id.desc())
        ):
            analysis_tasks.setdefault(task.entity_id, task)
    if resume_ids:
        for task in await db.scalars(
            select(ProcessingTask)
            .where(
                ProcessingTask.task_type == "PARSE_RESUME",
                ProcessingTask.entity_type == "RESUME_FILE",
                ProcessingTask.entity_id.in_(resume_ids),
            )
            .order_by(ProcessingTask.entity_id, ProcessingTask.created_at.desc(), ProcessingTask.id.desc())
        ):
            parse_tasks.setdefault(task.entity_id, task)
    evaluation_ids = [evaluation.id for evaluation in evaluations.values()]
    decisions: dict[int, HumanDecision] = {}
    if evaluation_ids:
        for decision_record in await db.scalars(
            select(HumanDecision)
            .where(HumanDecision.evaluation_id.in_(evaluation_ids))
            .order_by(HumanDecision.evaluation_id, HumanDecision.created_at.desc(), HumanDecision.id.desc())
        ):
            decisions.setdefault(decision_record.evaluation_id, decision_record)
    feedback_counts: dict[int, int] = {}
    if application_ids:
        for application_id, count in (await db.execute(
            select(InterviewFeedback.application_id, func.count())
            .where(InterviewFeedback.application_id.in_(application_ids))
            .group_by(InterviewFeedback.application_id)
        )).all():
            feedback_counts[application_id] = int(count)
    result = []
    for application in applications:
        resume = resumes.get(application.resume_file_id)
        candidate = candidates.get(application.candidate_id)
        parse = parses.get(application.resume_file_id)
        evaluation = evaluations.get(application.id)
        latest_analysis_task = analysis_tasks.get(application.id)
        parse_task = parse_tasks.get(application.resume_file_id)
        decision = decisions.get(evaluation.id) if evaluation is not None else None
        result.append({
            "application_id": application.id,
            "candidate_name": candidate.name_ciphertext if candidate else None,
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
            "interview_feedback_count": feedback_counts.get(application.id, 0),
            "uploaded_at": application.created_at,
        })
    return {"items": result, "total": total, "page": page, "page_size": page_size}


@router.get("/{job_id}/candidates/{application_id}/interview-feedback")
async def list_interview_feedback(
    job_id: int,
    application_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    await get_job_or_404(job_id, db, user)
    application = await db.get(JobApplication, application_id)
    if application is None or application.job_id != job_id:
        raise HTTPException(status_code=404, detail="候选人不存在")
    rows = (await db.execute(
        select(InterviewFeedback, User.display_name)
        .outerjoin(User, InterviewFeedback.interviewer_id == User.id)
        .where(InterviewFeedback.application_id == application_id)
        .order_by(InterviewFeedback.created_at.desc(), InterviewFeedback.id.desc())
    )).all()
    return [_serialize_interview_feedback(feedback, interviewer_name) for feedback, interviewer_name in rows]


@router.post("/{job_id}/candidates/{application_id}/interview-feedback", status_code=status.HTTP_201_CREATED)
async def create_interview_feedback(
    job_id: int,
    application_id: int,
    payload: InterviewFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    await get_job_or_404(job_id, db, user)
    application = await db.get(JobApplication, application_id)
    if application is None or application.job_id != job_id:
        raise HTTPException(status_code=404, detail="候选人不存在")
    result = payload.result.strip().upper()
    if result not in VALID_INTERVIEW_RESULTS:
        raise HTTPException(status_code=422, detail="无效的面试结论")
    feedback = InterviewFeedback(
        application_id=application_id,
        round_name=payload.round_name.strip(),
        result=result,
        dimension_feedback=payload.dimension_feedback or None,
        comment=payload.comment.strip() if payload.comment else None,
        interviewer_id=user.id,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return _serialize_interview_feedback(feedback, user.display_name)


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
    created, reused, skipped = [], [], []
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
            .where(
                CandidateEvaluation.application_id == application_id,
                CandidateEvaluation.parse_version_id == parse.id,
                CandidateEvaluation.requirement_version_id == job.active_requirement_version_id,
                CandidateEvaluation.status == "COMPLETED",
            )
            .order_by(CandidateEvaluation.created_at.desc(), CandidateEvaluation.id.desc())
            .limit(1)
        )
        if prior_evaluation is not None and not payload.confirm_reevaluate:
            reused.append(
                {"application_id": application_id, "evaluation_id": prior_evaluation.id}
            )
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
    return {"created": created, "reused": reused, "skipped": skipped}
