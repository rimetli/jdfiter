import hashlib
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.vision_ocr import extract_text_with_vision
from app.api.jobs import get_job_or_404
from app.core.auth import get_current_user
from app.core.config import get_settings
from app.db.models import (
    Candidate,
    CandidateIdentityClaim,
    JobApplication,
    ProcessingTask,
    ResumeFile,
    User,
)
from app.db.session import get_db
from app.schemas.resumes import ResumeUploadRead

router = APIRouter(prefix="/jobs", tags=["resumes"])
MAX_FILE_SIZE = 20 * 1024 * 1024
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
# OCR and exported PDFs often insert a space or dash between every phone digit.
PHONE_RE = re.compile(r"(?:(?:\+?\s*8\s*6)[-\s]?)?1[-\s]*[3-9](?:[-\s]*\d){9}")


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _hash(value: str | None) -> str | None:
    normalized = _normalize(value)
    if normalized is None:
        return None
    return hashlib.sha256(normalized.lower().encode("utf-8")).hexdigest()


def _normalize_phone(value: str | None) -> str | None:
    normalized = _normalize(value)
    if normalized is None:
        return None
    digits = re.sub(r"\D", "", normalized)
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits if len(digits) >= 7 else None


def _extract_text_from_pdf(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


RESUME_TITLE_WORDS = {
    "个人信息", "个人简历", "求职简历", "简历", "基本信息", "个人简介",
    "教育背景", "教育经历", "工作经历", "工作经验", "项目经历", "项目经验",
    "核心能力", "专业技能", "技能特长", "自我评价", "求职意向", "联系方式",
}

def _name_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem.strip()
    match = re.search(r"】\s*([一-龥]{2,4})(?:[\s·-]*\d+\s*年?)?\s*$", stem)
    if match:
        return match.group(1)
    match = re.search(r"([一-龥]{2,4})\s*[-·]\s*\d+\s*年", stem)
    if match:
        return match.group(1)
    match = re.match(r"^([一-龥]{2,4})(?:\s+|\s*[-_·]\s*)(?:简历|resume|cv)?", stem, re.IGNORECASE)
    if match and match.group(1) not in RESUME_TITLE_WORDS:
        return match.group(1)
    return None


def _looks_like_name(value: str) -> bool:
    if value in RESUME_TITLE_WORDS:
        return False
    return re.fullmatch(r"[一-龥]{2,4}", value) is not None


def _extract_identity(text: str, filename: str) -> tuple[str | None, str | None, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact_text = re.sub(r"\s+", "", text)
    email = EMAIL_RE.search(text) or EMAIL_RE.search(compact_text)
    phone = PHONE_RE.search(text) or PHONE_RE.search(compact_text)
    name = None
    for line in lines[:12]:
        cleaned = re.sub(r"^(姓名|Name|name)[:：\s]*", "", line).strip()
        if EMAIL_RE.search(cleaned) or PHONE_RE.search(cleaned):
            continue
        explicit = re.match(r"^(?:姓名|Name|name)[:：\s]*([一-龥]{2,4})(?=\s|$)", line)
        if explicit:
            name = explicit.group(1)
            break
        if _looks_like_name(cleaned):
            name = cleaned
            break
    if name is None or name in RESUME_TITLE_WORDS:
        name = _name_from_filename(filename) or name
    return name, email.group(0).lower() if email else None, _normalize_phone(phone.group(0) if phone else None)


async def _find_candidate_by_phone(
    db: AsyncSession, organization_id: int, phone_hash: str, owner_user_id: int
):
    return await db.scalar(
        select(Candidate).where(
            Candidate.organization_id == organization_id,
            Candidate.phone_hash == phone_hash,
            Candidate.owner_user_id == owner_user_id,
            Candidate.deleted_at.is_(None),
        )
    )


async def _find_candidate_by_email(
    db: AsyncSession, organization_id: int, email_hash: str, owner_user_id: int
):
    return await db.scalar(
        select(Candidate).where(
            Candidate.organization_id == organization_id,
            Candidate.email_hash == email_hash,
            Candidate.owner_user_id == owner_user_id,
            Candidate.deleted_at.is_(None),
        )
    )


async def _find_candidate_by_claim(
    db: AsyncSession, organization_id: int, owner_user_id: int, identity_type: str, identity_hash: str
) -> Candidate | None:
    return await db.scalar(
        select(Candidate)
        .join(CandidateIdentityClaim, CandidateIdentityClaim.candidate_id == Candidate.id)
        .where(
            CandidateIdentityClaim.organization_id == organization_id,
            CandidateIdentityClaim.owner_user_id == owner_user_id,
            CandidateIdentityClaim.identity_type == identity_type,
            CandidateIdentityClaim.identity_hash == identity_hash,
            Candidate.deleted_at.is_(None),
        )
    )


async def _claim_identity(
    db: AsyncSession,
    organization_id: int,
    owner_user_id: int,
    identity_type: str,
    identity_hash: str,
    candidate_id: int,
) -> None:
    db.add(
        CandidateIdentityClaim(
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            identity_type=identity_type,
            identity_hash=identity_hash,
            candidate_id=candidate_id,
        )
    )
    await db.flush()


async def _latest_resume_for_candidate(db: AsyncSession, candidate_id: int) -> ResumeFile | None:
    return await db.scalar(
        select(ResumeFile)
        .where(ResumeFile.candidate_id == candidate_id, ResumeFile.deleted_at.is_(None))
        .order_by(ResumeFile.created_at.desc(), ResumeFile.id.desc())
        .limit(1)
    )


async def _latest_task_for_resume(db: AsyncSession, resume_file_id: int) -> ProcessingTask | None:
    return await db.scalar(
        select(ProcessingTask)
        .where(
            ProcessingTask.task_type == "PARSE_RESUME",
            ProcessingTask.entity_type == "RESUME_FILE",
            ProcessingTask.entity_id == resume_file_id,
        )
        .order_by(ProcessingTask.created_at.desc(), ProcessingTask.id.desc())
        .limit(1)
    )


@router.post(
    "/{job_id}/resumes",
    response_model=ResumeUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    job_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeUploadRead:
    job = await get_job_or_404(job_id, db, user)
    # Save scalar ownership data before a rollback. SQLAlchemy expires ORM objects
    # after rollback; accessing user.id later can otherwise trigger async lazy IO.
    owner_user_id = user.id
    if job.status != "ACTIVE" or job.active_requirement_version_id is None:
        raise HTTPException(status_code=409, detail="请先发布岗位能力模型")

    filename = Path(file.filename or "resume.pdf").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="目前仅支持PDF简历")
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="PDF不能超过20MB")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="文件不是有效的PDF")

    ocr_used = False
    try:
        extracted_text = _extract_text_from_pdf(content)
    except (EOFError, PdfReadError, ValueError):
        extracted_text = ""
    if len(extracted_text) < 30:
        try:
            extracted_text = await extract_text_with_vision(content)
            ocr_used = True
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail="扫描版PDF视觉识别失败，请确认模型支持图片输入或上传清晰版PDF",
            ) from exc
    candidate_name, candidate_email, candidate_phone = _extract_identity(extracted_text, filename)
    # Hybrid PDFs may have selectable body text but render contact details as an
    # image. In that case pypdf succeeds, yet identity extraction still needs OCR.
    if (candidate_name is None or (candidate_phone is None and candidate_email is None)) and not ocr_used:
        try:
            vision_text = await extract_text_with_vision(content)
        except Exception:
            # Keep the original validation message if the optional fallback is
            # unavailable; it is clearer than exposing a model implementation error.
            pass
        else:
            extracted_text = f"{extracted_text}\n{vision_text}".strip()
            ocr_used = True
            candidate_name, candidate_email, candidate_phone = _extract_identity(
                extracted_text, filename
            )
    if candidate_name is None:
        raise HTTPException(status_code=422, detail="无法从PDF中识别姓名，暂不能上传")
    if candidate_phone is None and candidate_email is None:
        raise HTTPException(status_code=422, detail="无法从PDF中识别电话或邮箱，暂不能上传")

    name_hash = _hash(candidate_name)
    email_hash = _hash(candidate_email)
    phone_hash = _hash(candidate_phone)

    # 电话是首要唯一标识；只有完全没有电话时才使用邮箱。该身份会在数据库
    # 的 candidate_identity_claims 表中以唯一约束占位，阻止并发上传产生新候选人。
    identity_type, identity_hash = (
        ("phone", phone_hash) if phone_hash else ("email", email_hash)
    )
    existing_candidate = await _find_candidate_by_claim(
        db, job.organization_id, owner_user_id, identity_type, identity_hash
    )
    match_rule = identity_type
    # 去重规则：电话是候选人的首要唯一标识；仅在简历没有电话时才使用邮箱。
    # 姓名只用于展示和人工核验，避免同一人改名/简写后绕过重复校验。
    if existing_candidate is None and phone_hash:
        existing_candidate = await _find_candidate_by_phone(
            db, job.organization_id, phone_hash, owner_user_id
        )
    if existing_candidate is None and not candidate_phone and email_hash:
        existing_candidate = await _find_candidate_by_email(
            db, job.organization_id, email_hash, owner_user_id
        )
    if existing_candidate is None:
        match_rule = "new"

    digest = hashlib.sha256(content).hexdigest()

    settings = get_settings()
    organization_id = job.organization_id
    persisted_job_id = job.id
    candidate = existing_candidate
    created_candidate = False
    try:
        if candidate is None:
            candidate = Candidate(
                organization_id=organization_id,
                owner_user_id=owner_user_id,
                name_ciphertext=candidate_name,
                name_hash=name_hash,
                email_ciphertext=candidate_email,
                email_hash=email_hash,
                phone_ciphertext=candidate_phone,
                phone_hash=phone_hash,
                source="MANUAL_UPLOAD",
            )
            db.add(candidate)
            await db.flush()
            await _claim_identity(
                db, organization_id, owner_user_id, identity_type, identity_hash, candidate.id
            )
            created_candidate = True
        else:
            # Gradually establish claims for historical candidates encountered during upload.
            await _claim_identity(
                db, organization_id, owner_user_id, identity_type, identity_hash, candidate.id
            )
    except IntegrityError as exc:
        await db.rollback()
        candidate = await _find_candidate_by_claim(
            db, organization_id, owner_user_id, identity_type, identity_hash
        )
        if candidate is None:
            raise HTTPException(status_code=409, detail="候选人身份占位冲突，请稍后重试") from exc
        created_candidate = False
        match_rule = identity_type

    try:
        if created_candidate:
            relative_key = Path(str(organization_id)) / str(persisted_job_id) / f"{uuid4().hex}.pdf"
            storage_root = Path(settings.local_storage_path).resolve()
            target = storage_root / relative_key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            resume = ResumeFile(
                candidate_id=candidate.id,
                storage_key=str(relative_key),
                original_filename=filename,
                mime_type="application/pdf",
                size_bytes=len(content),
                sha256=digest,
                malware_status="PENDING",
                uploaded_by=owner_user_id,
            )
            db.add(resume)
            await db.flush()
            if ocr_used:
                preparsed_key = Path("preparsed") / f"{resume.id}.txt"
                preparsed_path = storage_root / preparsed_key
                preparsed_path.parent.mkdir(parents=True, exist_ok=True)
                preparsed_path.write_text(extracted_text, encoding="utf-8")
                resume.preparsed_text_storage_key = str(preparsed_key)
            application = JobApplication(
                job_id=persisted_job_id,
                candidate_id=candidate.id,
                resume_file_id=resume.id,
                stage="APPLIED",
                source="MANUAL_UPLOAD",
            )
            db.add(application)
            await db.flush()
            task = ProcessingTask(
                organization_id=job.organization_id,
                task_type="PARSE_RESUME",
                entity_type="RESUME_FILE",
                entity_id=resume.id,
                status="PENDING",
                progress=0,
                input_hash=digest,
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            duplicate = False
        else:
            resume = await _latest_resume_for_candidate(db, candidate.id)
            if resume is None:
                raise HTTPException(status_code=409, detail="已存在候选人但未找到简历记录")
            application = await db.scalar(
                select(JobApplication).where(
                    JobApplication.job_id == persisted_job_id,
                    JobApplication.candidate_id == candidate.id,
                    JobApplication.resume_file_id == resume.id,
                )
            )
            if application is None:
                application = JobApplication(
                    job_id=persisted_job_id,
                    candidate_id=candidate.id,
                    resume_file_id=resume.id,
                    stage="APPLIED",
                    source=f"DUPLICATE_{match_rule.upper()}",
                )
                db.add(application)
                await db.flush()
            task = await _latest_task_for_resume(db, resume.id)
            if task is None:
                task = ProcessingTask(
                    organization_id=job.organization_id,
                    task_type="PARSE_RESUME",
                    entity_type="RESUME_FILE",
                    entity_id=resume.id,
                    status="COMPLETED",
                    progress=100,
                    input_hash=resume.sha256,
                )
                db.add(task)
                await db.flush()
            duplicate = True
            await db.commit()
    except Exception:
        await db.rollback()
        if 'target' in locals():
            target.unlink(missing_ok=True)
        if 'preparsed_path' in locals():
            preparsed_path.unlink(missing_ok=True)
        raise

    return ResumeUploadRead(
        candidate_id=candidate.id,
        resume_file_id=resume.id,
        application_id=application.id,
        task_id=task.id,
        filename=filename,
        status=task.status,
        duplicate=duplicate,
        match_rule=match_rule,
    )
