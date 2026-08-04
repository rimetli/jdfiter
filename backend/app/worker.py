import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from socket import gethostname

from pypdf import PdfReader
from sqlalchemy import func, select

from app.ai.jd_analyzer import analyze_jd
from app.ai.resume_analyzer import (
    ResumeProfile,
    analyze_and_match,
    match_resume,
)
from app.ai.vision_ocr import extract_text_with_vision
from app.core.config import get_settings
from app.core.task_policy import retry_available_after
from app.db.models import (
    CandidateEvaluation,
    EvaluationEvidence,
    EvaluationScoreDetail,
    JobApplication,
    JobPosition,
    JobRequirementVersion,
    ProcessingTask,
    RequirementItem,
    ResumeFile,
    ResumeParseVersion,
)
from app.db.session import SessionLocal, engine
from app.services.job_analysis import create_jd_requirement_draft

WORKER_ID = f"{gethostname()}-{id(object())}"
MAX_CONCURRENCY = 8

DEPTH_ROLE_FACTOR = {
    ("MET", "DEEP", "LEAD"): Decimal("1.0"),
    ("MET", "DEEP", "CONTRIBUTOR"): Decimal("0.8"),
    ("MET", "SHALLOW", "LEAD"): Decimal("0.7"),
    ("MET", "SHALLOW", "CONTRIBUTOR"): Decimal("0.5"),
    ("MET", "DEEP", "EXPOSURE"): Decimal("0.4"),
    ("MET", "SHALLOW", "EXPOSURE"): Decimal("0.3"),
}

# PARTIAL 代表只有部分岗位证据，仍需根据证据深度和实际角色拉开差距。
PARTIAL_DEPTH_ROLE_FACTOR = {
    ("DEEP", "LEAD"): Decimal("0.6"),
    ("DEEP", "CONTRIBUTOR"): Decimal("0.5"),
    ("DEEP", "EXPOSURE"): Decimal("0.4"),
    ("SHALLOW", "LEAD"): Decimal("0.4"),
    ("SHALLOW", "CONTRIBUTOR"): Decimal("0.3"),
    ("SHALLOW", "EXPOSURE"): Decimal("0.25"),
}
SCORING_POLICY_VERSION = "depth-role-1.1.0"


def score_factor(status: str, depth: str | None, role: str | None) -> Decimal:
    if status in {"UNKNOWN", "NOT_MET"}:
        return Decimal(0)
    if status == "PARTIAL":
        return PARTIAL_DEPTH_ROLE_FACTOR.get((depth, role), Decimal("0.3"))
    return DEPTH_ROLE_FACTOR.get((status, depth, role), Decimal("0.5"))


def credibility_adjustment(
    items: list, by_code: dict, total: Decimal
) -> tuple[Decimal, list[str]]:
    """全维度最高档时施加可信度校准，抑制包装简历虚高分。"""
    deep_lead_count = sum(
        1
        for item in items
        if by_code[item.dimension_code].status == "MET"
        and by_code[item.dimension_code].depth == "DEEP"
        and by_code[item.dimension_code].role == "LEAD"
    )
    warnings = []
    met_count = sum(
        1 for item in items if by_code[item.dimension_code].status == "MET"
    )
    if met_count == len(items) and deep_lead_count == len(items):
        total = (total * Decimal("0.7")).quantize(Decimal("0.01"))
        warnings.append(
            "全维度均判为深度实践+主导，存在过度包装风险，已施加可信度校准(×0.7)，建议面试重点核验实际贡献"
        )
    elif deep_lead_count >= len(items) - 1 and total >= Decimal(90):
        total = (total * Decimal("0.85")).quantize(Decimal("0.01"))
        warnings.append(
            f"{deep_lead_count}/{len(items)} 维度判为深度实践+主导，存在过度包装风险，已施加可信度校准(×0.85)，建议面试核验关键维度的实际贡献深度"
        )
    return total, warnings


async def claim_task() -> int | None:
    async with SessionLocal() as db, db.begin():
        task = await db.scalar(
            select(ProcessingTask)
            .where(
                ProcessingTask.status == "PENDING",
                ProcessingTask.available_at <= func.now(),
            )
            .order_by(ProcessingTask.priority, ProcessingTask.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task is None:
            return None
        task.status = "PROCESSING"
        task.progress = 5
        task.locked_by = WORKER_ID
        task.locked_at = datetime.utcnow()
        task.started_at = task.started_at or datetime.utcnow()
        task.attempt_count += 1
        return task.id


async def recover_stale_tasks() -> int:
    """Requeue expired worker leases, or permanently fail exhausted tasks."""
    settings = get_settings()
    now = datetime.utcnow()
    expired_before = now - timedelta(seconds=settings.task_lease_seconds)
    recovered = 0
    async with SessionLocal() as db:
        tasks = list(
            await db.scalars(
                select(ProcessingTask).where(
                    ProcessingTask.status == "PROCESSING",
                    ProcessingTask.locked_at.is_not(None),
                    ProcessingTask.locked_at < expired_before,
                )
            )
        )
        for task in tasks:
            task.locked_by = None
            task.locked_at = None
            task.error_code = "WORKER_LEASE_EXPIRED"
            task.error_message_safe = "任务工作租约超时，已回收"
            if task.attempt_count >= settings.task_max_attempts:
                task.status = "FAILED"
                task.completed_at = now
            else:
                task.status = "PENDING"
                task.progress = 0
                task.available_at = now + retry_available_after(
                    task.attempt_count,
                    settings.task_retry_base_seconds,
                    settings.task_retry_max_seconds,
                )
            recovered += 1
        if recovered:
            await db.commit()
    return recovered


async def heartbeat_task(task_id: int, stop: asyncio.Event) -> None:
    """Renew the task lease while a long OCR or model call is running."""
    interval = max(get_settings().task_heartbeat_seconds, 1)
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            async with SessionLocal() as db:
                task = await db.get(ProcessingTask, task_id)
                if task is None or task.status != "PROCESSING" or task.locked_by != WORKER_ID:
                    return
                task.locked_at = datetime.utcnow()
                await db.commit()


def extract_pdf_text(path: Path) -> tuple[str, int]:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip(), len(pages)


async def process_resume(task_id: int) -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        task = await db.get(ProcessingTask, task_id)
        if task is None:
            return
        resume = await db.get(ResumeFile, task.entity_id)
        if resume is None:
            raise ValueError("简历文件记录不存在")
        storage_root = Path(settings.local_storage_path).resolve()
        source = storage_root / resume.storage_key
        ocr_used = bool(resume.preparsed_text_storage_key)
        if resume.preparsed_text_storage_key:
            text = (storage_root / resume.preparsed_text_storage_key).read_text(encoding="utf-8")
            page_count = len(PdfReader(source).pages)
        else:
            text, page_count = await asyncio.to_thread(extract_pdf_text, source)
        if len(text) < 30:
            text = await extract_text_with_vision(source.read_bytes())
            ocr_used = True
        text = text.encode("utf-8", errors="replace").decode("utf-8")
        task.progress = 40
        await db.commit()
        profile = ResumeProfile()
        latest = await db.scalar(
            select(func.max(ResumeParseVersion.version_no)).where(
                ResumeParseVersion.resume_file_id == resume.id
            )
        )
        parsed_key = Path("parsed") / f"{resume.id}-v{(latest or 0) + 1}.txt"
        parsed_path = Path(settings.local_storage_path).resolve() / parsed_key
        parsed_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_path.write_text(text, encoding="utf-8")
        parse_version = ResumeParseVersion(
            resume_file_id=resume.id,
            version_no=(latest or 0) + 1,
            status="COMPLETED",
            parser_version="pypdf-1.0.0",
            ocr_used=ocr_used,
            normalized_text_storage_key=str(parsed_key),
            profile_json={
                **profile.model_dump(),
                "page_count": page_count,
                "ai_analysis_status": "PENDING_BATCH_ANALYSIS",
            },
            validation_errors=[],
            started_at=task.started_at,
            completed_at=datetime.utcnow(),
        )
        db.add(parse_version)
        task.status = "COMPLETED"
        task.progress = 100
        task.completed_at = datetime.utcnow()
        task.locked_by = None
        task.locked_at = None
        await db.commit()


async def process_job_jd_analysis(task_id: int) -> None:
    async with SessionLocal() as db:
        task = await db.get(ProcessingTask, task_id)
        job = await db.get(JobPosition, task.entity_id) if task is not None else None
        if task is None or job is None:
            raise ValueError("岗位不存在")
        analysis = await analyze_jd(job.jd_content)
        task.progress = 85
        await create_jd_requirement_draft(db, job, analysis, created_by=job.created_by)
        task.status = "COMPLETED"
        task.progress = 100
        task.completed_at = datetime.utcnow()
        task.locked_by = None
        task.locked_at = None
        await db.commit()


def _cached_profile(parse_version: ResumeParseVersion) -> ResumeProfile | None:
    data = parse_version.profile_json or {}
    if data.get("ai_analysis_status") != "COMPLETED":
        return None
    try:
        return ResumeProfile.model_validate(
            {key: value for key, value in data.items() if key in ResumeProfile.model_fields}
        )
    except Exception:  # noqa: BLE001 - 缓存损坏时回退到重新分析
        return None


async def process_evaluation(task_id: int) -> None:
    settings = get_settings()
    if not settings.resume_llm_enabled:
        raise ValueError("简历模型分析未授权或未启用")
    async with SessionLocal() as db:
        task = await db.get(ProcessingTask, task_id)
        application = await db.get(JobApplication, task.entity_id) if task else None
        if task is None or application is None:
            raise ValueError("申请记录不存在")
        job = await db.get(JobPosition, application.job_id)
        if job is None or job.active_requirement_version_id is None:
            raise ValueError("岗位能力模型未发布")
        parse_version = await db.scalar(
            select(ResumeParseVersion)
            .where(
                ResumeParseVersion.resume_file_id == application.resume_file_id,
                ResumeParseVersion.status == "COMPLETED",
            )
            .order_by(ResumeParseVersion.version_no.desc())
            .limit(1)
        )
        if parse_version is None or not parse_version.normalized_text_storage_key:
            raise ValueError("简历尚未解析完成")
        text_path = Path(settings.local_storage_path).resolve() / parse_version.normalized_text_storage_key
        text = text_path.read_text(encoding="utf-8")
        task.progress = 15
        await db.commit()

        items = list(
            await db.scalars(
                select(RequirementItem)
                .where(RequirementItem.requirement_version_id == job.active_requirement_version_id)
                .order_by(RequirementItem.sort_order)
            )
        )
        requirements = [
            {
                "code": item.dimension_code,
                "name": item.name,
                "description": item.description,
                "is_gate": item.is_gate,
                "max_score": float(item.max_score),
                "evidence_rule": item.evidence_rule,
            }
            for item in items
        ]

        profile = _cached_profile(parse_version)
        if profile is not None:
            matched = await match_resume(text, requirements)
        else:
            profile, matched = await analyze_and_match(text, requirements)
            parse_version.profile_json = {
                **profile.model_dump(),
                "page_count": (parse_version.profile_json or {}).get("page_count"),
                "ai_analysis_status": "COMPLETED",
            }
        task.progress = 80

        by_code = {item.code: item for item in matched.dimensions}
        factors = {
            item.dimension_code: score_factor(
                by_code[item.dimension_code].status,
                by_code[item.dimension_code].depth,
                by_code[item.dimension_code].role,
            )
            for item in items
        }
        total = sum((item.max_score * factors[item.dimension_code] for item in items), Decimal(0))
        total, credibility_warnings = credibility_adjustment(items, by_code, total)
        gate_statuses = [by_code[item.dimension_code].status for item in items if item.is_gate]
        gate_result = "PASSED"
        if any(value == "NOT_MET" for value in gate_statuses):
            gate_result = "NOT_MET"
        elif any(value in {"UNKNOWN", "PARTIAL"} for value in gate_statuses):
            gate_result = "REVIEW_REQUIRED"
        level = "STRONGLY_RECOMMENDED" if total >= 85 else "RECOMMENDED" if total >= 70 else "REVIEW" if total >= 60 else "LOW_MATCH"
        if gate_result != "PASSED" and level in {"STRONGLY_RECOMMENDED", "RECOMMENDED"}:
            level = "REVIEW"
        previous = await db.scalar(
            select(CandidateEvaluation)
            .where(CandidateEvaluation.application_id == application.id)
            .order_by(CandidateEvaluation.created_at.desc())
            .limit(1)
        )
        version = await db.get(JobRequirementVersion, job.active_requirement_version_id)
        shallow_met = [
            f"{item.name}：证据偏泛，建议面试深挖实际贡献与量化成果"
            for item in items
            if by_code[item.dimension_code].status == "MET"
            and by_code[item.dimension_code].depth == "SHALLOW"
        ]
        shallow_met = shallow_met + credibility_warnings
        evaluation = CandidateEvaluation(
            application_id=application.id,
            parse_version_id=parse_version.id,
            requirement_version_id=job.active_requirement_version_id,
            status="COMPLETED",
            total_score=total,
            level=level,
            gate_result=gate_result,
            summary_json={
                "advantages": [x.reason for x in matched.dimensions if x.status == "MET"],
                "risks": [x.reason for x in matched.dimensions if x.status == "NOT_MET"] + shallow_met,
                "unknowns": [x.reason for x in matched.dimensions if x.status == "UNKNOWN"],
            },
            confidence=Decimal(
                str(sum(x.confidence for x in matched.dimensions) / len(matched.dimensions))
            ).quantize(Decimal("0.001")),
            rubric_version=version.rubric_version if version else "1.0.0",
            prompt_version="resume-match-1.1.0",
            model_provider="openai-compatible",
            model_name=settings.llm_model,
            supersedes_evaluation_id=previous.id if previous else None,
            completed_at=datetime.utcnow(),
        )
        db.add(evaluation)
        await db.flush()
        for item in items:
            match = by_code[item.dimension_code]
            factor = factors[item.dimension_code]
            detail = EvaluationScoreDetail(
                evaluation_id=evaluation.id,
                dimension_code=item.dimension_code,
                item_code=item.item_code,
                status=match.status,
                depth=match.depth,
                role=match.role,
                score=item.max_score * factor,
                max_score=item.max_score,
                confidence=Decimal(str(match.confidence)).quantize(Decimal("0.001")),
                reason=match.reason,
                calculation_json={
                    "factor": float(factor),
                    "status": match.status,
                    "depth": match.depth,
                    "role": match.role,
                    "scoring_policy_version": SCORING_POLICY_VERSION,
                },
            )
            db.add(detail)
            await db.flush()
            for quote in match.evidence[:5]:
                db.add(EvaluationEvidence(
                    score_detail_id=detail.id,
                    parse_version_id=parse_version.id,
                    page_no=1,
                    quote_text=quote[:2000],
                    evidence_type="DIRECT",
                ))
        task.status = "COMPLETED"
        task.progress = 100
        task.completed_at = datetime.utcnow()
        task.locked_by = None
        task.locked_at = None
        await db.commit()


async def fail_task(task_id: int, exc: Exception) -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        task = await db.get(ProcessingTask, task_id)
        if task is None:
            return
        task.error_code = type(exc).__name__
        task.error_message_safe = str(exc)[:500]
        task.locked_by = None
        task.locked_at = None
        if task.attempt_count >= settings.task_max_attempts:
            task.status = "FAILED"
            task.completed_at = datetime.utcnow()
        else:
            task.status = "PENDING"
            task.progress = 0
            task.available_at = datetime.utcnow() + retry_available_after(
                task.attempt_count,
                settings.task_retry_base_seconds,
                settings.task_retry_max_seconds,
            )
            task.completed_at = None
        await db.commit()


async def execute_task(task_id: int) -> None:
    heartbeat_stop = asyncio.Event()
    heartbeat = asyncio.create_task(heartbeat_task(task_id, heartbeat_stop))
    try:
        async with SessionLocal() as db:
            claimed = await db.get(ProcessingTask, task_id)
            task_type = claimed.task_type if claimed else None
        if task_type == "PARSE_RESUME":
            await process_resume(task_id)
        elif task_type == "ANALYZE_JOB_JD":
            await process_job_jd_analysis(task_id)
        elif task_type == "ANALYZE_APPLICATION":
            await process_evaluation(task_id)
        else:
            raise ValueError(f"不支持的任务类型：{task_type}")
        print(f"Task {task_id} completed", flush=True)
    except Exception as exc:  # noqa: BLE001 - worker must persist every task failure
        await fail_task(task_id, exc)
        print(f"Task {task_id} failed: {type(exc).__name__}", flush=True)
    finally:
        heartbeat_stop.set()
        await heartbeat


async def run_worker() -> None:
    print(f"Resume worker started: {WORKER_ID} (concurrency={MAX_CONCURRENCY})", flush=True)
    running: set[asyncio.Task] = set()
    last_recovery: datetime | None = None
    try:
        while True:
            if last_recovery is None or (datetime.utcnow() - last_recovery).total_seconds() >= 30:
                recovered = await recover_stale_tasks()
                if recovered:
                    print(f"Recovered {recovered} expired task lease(s)", flush=True)
                last_recovery = datetime.utcnow()
            while len(running) < MAX_CONCURRENCY:
                task_id = await claim_task()
                if task_id is None:
                    break
                running.add(asyncio.create_task(execute_task(task_id)))
            if running:
                done, running = await asyncio.wait(
                    running, return_when=asyncio.FIRST_COMPLETED
                )
                for finished in done:
                    if finished.exception() is not None:
                        print(f"Worker coroutine error: {finished.exception()}", flush=True)
            else:
                await asyncio.sleep(2)
    finally:
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_worker())
