from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.jd_analyzer import DIMENSIONS, JDAnalysis
from app.db.models import JobPosition, JobRequirementVersion, RequirementItem


async def create_jd_requirement_draft(
    db: AsyncSession, job: JobPosition, analysis: JDAnalysis, *, created_by: int
) -> JobRequirementVersion:
    """Persist a completed JD analysis as an editable requirement draft."""
    latest = await db.scalar(
        select(func.max(JobRequirementVersion.version_no)).where(
            JobRequirementVersion.job_id == job.id
        )
    )
    weights = {code: score for code, (_, score) in DIMENSIONS.items()}
    version = JobRequirementVersion(
        job_id=job.id,
        version_no=(latest or 0) + 1,
        summary=analysis.summary,
        rubric_version="1.0.0",
        weight_config=weights,
        status="DRAFT",
        created_by=created_by,
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
    return version
