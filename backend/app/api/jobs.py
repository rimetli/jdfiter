from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.jd_analyzer import DIMENSIONS, analyze_jd
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


@router.get("", response_model=list[JobRead])
async def list_jobs(
    organization_id: int = Query(...),
    job_status: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[JobPosition]:
    if organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="无权访问该组织")
    statement = select(JobPosition).where(
        JobPosition.organization_id == organization_id,
        JobPosition.archived_at.is_(None),
    )
    if job_status:
        statement = statement.where(JobPosition.status == job_status)
    if user.role != "ADMIN":
        statement = statement.where(JobPosition.created_by == user.id)
    result = await db.scalars(statement.order_by(JobPosition.updated_at.desc()))
    return list(result)


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
        ]
    )


@router.post(
    "/{job_id}/analyze-jd",
    response_model=RequirementVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_job_jd(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRequirementVersion:
    job = await get_job_or_404(job_id, db, user)
    try:
        analysis = await analyze_jd(job.jd_content)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型分析失败：{type(exc).__name__}") from exc

    latest = await db.scalar(
        select(func.max(JobRequirementVersion.version_no)).where(
            JobRequirementVersion.job_id == job_id
        )
    )
    weights = {code: score for code, (_, score) in DIMENSIONS.items()}
    version = JobRequirementVersion(
        job_id=job_id,
        version_no=(latest or 0) + 1,
        summary=analysis.summary,
        rubric_version="1.0.0",
        weight_config=weights,
        status="DRAFT",
        created_by=user.id,
    )
    db.add(version)
    await db.flush()
    by_code = {item.code: item for item in analysis.dimensions}
    db.add_all(
        [
            RequirementItem(
                requirement_version_id=version.id,
                dimension_code=code,
                item_code=code,
                name=name,
                description=by_code[code].description,
                requirement_type="MUST_HAVE" if by_code[code].is_gate else "NICE_HAVE",
                max_score=score,
                is_gate=by_code[code].is_gate,
                acceptable_alternatives=by_code[code].acceptable_alternatives,
                evidence_rule=by_code[code].evidence_rule,
                sort_order=index,
            )
            for index, (code, (name, score)) in enumerate(DIMENSIONS.items())
        ]
    )
    job.status = "REVIEW"
    await db.commit()
    await db.refresh(version)
    return version


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
