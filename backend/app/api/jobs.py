import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.db.models import (
    Candidate,
    CandidateEvaluation,
    CandidateIdentityClaim,
    EvaluationEvidence,
    EvaluationScoreDetail,
    HumanDecision,
    InterviewFeedback,
    JobApplication,
    JobPosition,
    JobRequirementVersion,
    PendingResumeUpload,
    ProcessingTask,
    RequirementItem,
    ResumeFile,
    ResumeParseVersion,
    User,
)
from app.db.session import get_db
from app.schemas.jobs import (
    JobCreate,
    JobRead,
    JobUpdate,
    RequirementScoresUpdate,
    RequirementVersionCreate,
    RequirementVersionDetail,
    RequirementVersionRead,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


async def get_job_or_404(
    job_id: int, db: AsyncSession, user: User | None = None
) -> JobPosition:
    job = await db.get(JobPosition, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    if user is not None and user.role != "ADMIN" and job.created_by != user.id:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return job


def _remove_local_resume_files(storage_keys: list[str | None]) -> None:
    storage_root = Path(get_settings().local_storage_path).resolve()
    for storage_key in storage_keys:
        if not storage_key:
            continue
        target = (storage_root / storage_key).resolve()
        if storage_root not in target.parents:
            continue
        try:
            target.unlink(missing_ok=True)
        except OSError:
            # Database records are already removed. A stale local file is safer
            # than failing a completed deletion or touching a path outside storage.
            continue


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> JobPosition:
    if payload.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="无权创建其他组织的岗位")
    job = JobPosition(**payload.model_dump(), status="DRAFT", created_by=user.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.get("")
async def list_jobs(
    organization_id: int = Query(...),
    job_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="无权访问该组织")
    statement = select(JobPosition, User.display_name).outerjoin(
        User, JobPosition.created_by == User.id
    ).where(
        JobPosition.organization_id == organization_id,
        JobPosition.archived_at.is_(None),
    )
    if job_status:
        statement = statement.where(JobPosition.status == job_status)
    if user.role != "ADMIN":
        statement = statement.where(JobPosition.created_by == user.id)
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    result = await db.execute(
        statement.order_by(JobPosition.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [
        JobRead.model_validate(job).model_copy(update={"owner_name": owner_name})
        for job, owner_name in result.all()
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{job_id}", response_model=JobRead)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> JobPosition:
    return await get_job_or_404(job_id, db, user)


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: int,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobPosition:
    job = await get_job_or_404(job_id, db, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    await db.commit()
    await db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    """Remove a job and its exclusive resume data while preserving shared candidates."""
    job = await get_job_or_404(job_id, db, user)

    pending_uploads = list(
        await db.scalars(select(PendingResumeUpload).where(PendingResumeUpload.job_id == job_id))
    )
    pending_ids = [upload.id for upload in pending_uploads]
    if pending_ids:
        await db.execute(
            delete(ProcessingTask).where(
                ProcessingTask.task_type == "PROCESS_RESUME_UPLOAD",
                ProcessingTask.entity_type == "PENDING_RESUME_UPLOAD",
                ProcessingTask.entity_id.in_(pending_ids),
            )
        )
        await db.execute(delete(PendingResumeUpload).where(PendingResumeUpload.id.in_(pending_ids)))

    applications = list(
        await db.scalars(select(JobApplication).where(JobApplication.job_id == job_id))
    )
    application_ids = [application.id for application in applications]
    candidate_ids = {application.candidate_id for application in applications}
    resume_ids = {application.resume_file_id for application in applications}
    shared_resume_ids: set[int] = set()
    if resume_ids:
        shared_resume_ids = set(
            await db.scalars(
                select(JobApplication.resume_file_id).where(
                    JobApplication.resume_file_id.in_(resume_ids),
                    JobApplication.job_id != job_id,
                )
            )
        )
    removable_resume_ids = resume_ids - shared_resume_ids
    removable_resumes: list[ResumeFile] = []
    parse_versions: list[ResumeParseVersion] = []
    if removable_resume_ids:
        removable_resumes = list(
            await db.scalars(select(ResumeFile).where(ResumeFile.id.in_(removable_resume_ids)))
        )
        parse_versions = list(
            await db.scalars(
                select(ResumeParseVersion).where(
                    ResumeParseVersion.resume_file_id.in_(removable_resume_ids)
                )
            )
        )
    evaluation_ids: list[int] = []
    if application_ids:
        evaluation_ids = list(
            await db.scalars(
                select(CandidateEvaluation.id).where(
                    CandidateEvaluation.application_id.in_(application_ids)
                )
            )
        )
    if evaluation_ids:
        await db.execute(
            update(CandidateEvaluation)
            .where(CandidateEvaluation.supersedes_evaluation_id.in_(evaluation_ids))
            .values(supersedes_evaluation_id=None)
        )
        detail_ids = list(
            await db.scalars(
                select(EvaluationScoreDetail.id).where(
                    EvaluationScoreDetail.evaluation_id.in_(evaluation_ids)
                )
            )
        )
        if detail_ids:
            await db.execute(
                delete(EvaluationEvidence).where(EvaluationEvidence.score_detail_id.in_(detail_ids))
            )
        await db.execute(
            delete(HumanDecision).where(HumanDecision.evaluation_id.in_(evaluation_ids))
        )
        await db.execute(
            delete(EvaluationScoreDetail).where(EvaluationScoreDetail.evaluation_id.in_(evaluation_ids))
        )
        await db.execute(
            delete(CandidateEvaluation).where(CandidateEvaluation.id.in_(evaluation_ids))
        )
    if application_ids:
        await db.execute(
            delete(InterviewFeedback).where(InterviewFeedback.application_id.in_(application_ids))
        )
        await db.execute(
            delete(ProcessingTask).where(
                ProcessingTask.task_type == "ANALYZE_APPLICATION",
                ProcessingTask.entity_type == "JOB_APPLICATION",
                ProcessingTask.entity_id.in_(application_ids),
            )
        )
        await db.execute(delete(JobApplication).where(JobApplication.id.in_(application_ids)))

    if removable_resume_ids:
        await db.execute(
            delete(ProcessingTask).where(
                ProcessingTask.task_type == "PARSE_RESUME",
                ProcessingTask.entity_type == "RESUME_FILE",
                ProcessingTask.entity_id.in_(removable_resume_ids),
            )
        )
        await db.execute(
            delete(ResumeParseVersion).where(
                ResumeParseVersion.resume_file_id.in_(removable_resume_ids)
            )
        )
        await db.execute(delete(ResumeFile).where(ResumeFile.id.in_(removable_resume_ids)))

    if candidate_ids:
        remaining_candidate_ids = set(
            await db.scalars(
                select(ResumeFile.candidate_id).where(ResumeFile.candidate_id.in_(candidate_ids))
            )
        )
        remaining_candidate_ids.update(
            await db.scalars(
                select(JobApplication.candidate_id).where(JobApplication.candidate_id.in_(candidate_ids))
            )
        )
        removable_candidate_ids = candidate_ids - remaining_candidate_ids
        if removable_candidate_ids:
            await db.execute(
                delete(CandidateIdentityClaim).where(
                    CandidateIdentityClaim.candidate_id.in_(removable_candidate_ids)
                )
            )
            await db.execute(delete(Candidate).where(Candidate.id.in_(removable_candidate_ids)))

    requirement_ids = list(
        await db.scalars(
            select(JobRequirementVersion.id).where(JobRequirementVersion.job_id == job_id)
        )
    )
    if requirement_ids:
        await db.execute(
            delete(RequirementItem).where(RequirementItem.requirement_version_id.in_(requirement_ids))
        )
        await db.execute(
            delete(JobRequirementVersion).where(JobRequirementVersion.id.in_(requirement_ids))
        )
    await db.delete(job)
    await db.commit()
    _remove_local_resume_files(
        [
            *(resume.storage_key for resume in removable_resumes),
            *(resume.preparsed_text_storage_key for resume in removable_resumes),
            *(version.normalized_text_storage_key for version in parse_versions),
            *(upload.storage_key for upload in pending_uploads),
        ]
    )


@router.post(
    "/{job_id}/analyze-jd",
    status_code=status.HTTP_202_ACCEPTED,
)
async def analyze_job_jd(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    job = await get_job_or_404(job_id, db, user)
    existing = await db.scalar(
        select(ProcessingTask)
        .where(
            ProcessingTask.task_type == "ANALYZE_JOB_JD",
            ProcessingTask.entity_type == "JOB_POSITION",
            ProcessingTask.entity_id == job.id,
            ProcessingTask.status.in_(["PENDING", "PROCESSING"]),
        )
        .order_by(ProcessingTask.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return {"task_id": existing.id, "status": existing.status, "reused": True}

    task = ProcessingTask(
        organization_id=job.organization_id,
        task_type="ANALYZE_JOB_JD",
        entity_type="JOB_POSITION",
        entity_id=job.id,
        status="PENDING",
        progress=0,
        input_hash=hashlib.sha256(job.jd_content.encode("utf-8")).hexdigest(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {"task_id": task.id, "status": task.status, "reused": False}


@router.get(
    "/{job_id}/requirement-versions",
    response_model=list[RequirementVersionRead],
)
async def list_requirement_versions(
    job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[JobRequirementVersion]:
    await get_job_or_404(job_id, db, user)
    result = await db.scalars(
        select(JobRequirementVersion)
        .where(JobRequirementVersion.job_id == job_id)
        .order_by(JobRequirementVersion.version_no.desc())
    )
    return list(result)


@router.get(
    "/{job_id}/requirement-versions/{version_id}",
    response_model=RequirementVersionDetail,
)
async def get_requirement_version(
    job_id: int, version_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    await get_job_or_404(job_id, db, user)
    version = await db.get(JobRequirementVersion, version_id)
    if version is None or version.job_id != job_id:
        raise HTTPException(status_code=404, detail="能力模型版本不存在")
    items = list(
        await db.scalars(
            select(RequirementItem)
            .where(RequirementItem.requirement_version_id == version_id)
            .order_by(RequirementItem.sort_order)
        )
    )
    return {
        "id": version.id,
        "job_id": version.job_id,
        "version_no": version.version_no,
        "summary": version.summary,
        "rubric_version": version.rubric_version,
        "weight_config": version.weight_config,
        "status": version.status,
        "created_at": version.created_at,
        "published_at": version.published_at,
        "items": items,
    }


@router.patch(
    "/{job_id}/requirement-versions/{version_id}/scores",
    response_model=RequirementVersionDetail,
)
async def update_requirement_scores(
    job_id: int,
    version_id: int,
    payload: RequirementScoresUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    await get_job_or_404(job_id, db, user)
    version = await db.get(JobRequirementVersion, version_id)
    if version is None or version.job_id != job_id:
        raise HTTPException(status_code=404, detail="能力模型版本不存在")
    if version.status != "DRAFT":
        raise HTTPException(status_code=409, detail="已发布版本不能修改")

    items = list(
        await db.scalars(
            select(RequirementItem)
            .where(RequirementItem.requirement_version_id == version_id)
            .order_by(RequirementItem.sort_order)
        )
    )
    current_ids = {item.id for item in items}
    incoming_ids = {item.item_id for item in payload.items}
    if current_ids != incoming_ids:
        raise HTTPException(status_code=422, detail="必须提交该版本的全部能力项")
    score_by_id = {item.item_id: item.max_score for item in payload.items}
    for item in items:
        item.max_score = score_by_id[item.id]
    version.weight_config = {
        item.dimension_code: float(score_by_id[item.id]) for item in items
    }
    await db.commit()
    await db.refresh(version)
    return {
        "id": version.id,
        "job_id": version.job_id,
        "version_no": version.version_no,
        "summary": version.summary,
        "rubric_version": version.rubric_version,
        "weight_config": version.weight_config,
        "status": version.status,
        "created_at": version.created_at,
        "published_at": version.published_at,
        "items": items,
    }


@router.post(
    "/{job_id}/requirement-versions",
    response_model=RequirementVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_requirement_version(
    job_id: int,
    payload: RequirementVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRequirementVersion:
    job = await get_job_or_404(job_id, db, user)
    latest = await db.scalar(
        select(func.max(JobRequirementVersion.version_no)).where(
            JobRequirementVersion.job_id == job_id
        )
    )
    version = JobRequirementVersion(
        job_id=job_id,
        version_no=(latest or 0) + 1,
        summary=payload.summary,
        rubric_version=payload.rubric_version,
        weight_config={key: float(value) for key, value in payload.weight_config.items()},
        status="DRAFT",
        created_by=user.id,
    )
    db.add(version)
    await db.flush()
    db.add_all(
        [
            RequirementItem(requirement_version_id=version.id, **item.model_dump())
            for item in payload.items
        ]
    )
    job.status = "REVIEW"
    await db.commit()
    await db.refresh(version)
    return version


@router.post(
    "/{job_id}/requirement-versions/{version_id}/publish",
    response_model=RequirementVersionRead,
)
async def publish_requirement_version(
    job_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRequirementVersion:
    job = await get_job_or_404(job_id, db, user)
    version = await db.get(JobRequirementVersion, version_id)
    if version is None or version.job_id != job_id:
        raise HTTPException(status_code=404, detail="能力模型版本不存在")
    if version.status == "PUBLISHED":
        return version
    version.status = "PUBLISHED"
    version.published_at = datetime.utcnow()
    job.active_requirement_version_id = version.id
    job.status = "ACTIVE"
    await db.commit()
    await db.refresh(version)
    return version
