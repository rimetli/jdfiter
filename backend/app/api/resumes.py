import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.jobs import get_job_or_404
from app.core.auth import get_current_user
from app.core.config import get_settings
from app.db.models import JobApplication, PendingResumeUpload, ProcessingTask, ResumeFile, User
from app.db.session import get_db
from app.schemas.resumes import ResumeUploadRead
from app.services.resume_identity import extract_identity

router = APIRouter(prefix="/jobs", tags=["resumes"])
MAX_FILE_SIZE = 20 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _extract_identity(text: str, filename: str) -> tuple[str | None, str | None, str | None]:
    """Compatibility wrapper for existing identity extraction tests and scripts."""
    return extract_identity(text, filename)


async def _stream_pdf_to_storage(file: UploadFile, target: Path) -> tuple[int, str]:
    """Persist an upload in bounded chunks; OCR and PDF parsing belong to the Worker."""
    digest = hashlib.sha256()
    total = 0
    first_chunk = b""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as destination:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                if not first_chunk:
                    first_chunk = chunk
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="PDF不能超过20MB")
                digest.update(chunk)
                destination.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    if not first_chunk.startswith(b"%PDF-"):
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=415, detail="文件不是有效的PDF")
    return total, digest.hexdigest()


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
    """Accept quickly, then let the Worker OCR, validate identity and deduplicate."""
    job = await get_job_or_404(job_id, db, user)
    if job.status != "ACTIVE" or job.active_requirement_version_id is None:
        raise HTTPException(status_code=409, detail="请先发布岗位能力模型")

    filename = Path(file.filename or "resume.pdf").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="目前仅支持PDF简历")

    settings = get_settings()
    relative_key = Path("pending") / str(job.organization_id) / str(job.id) / f"{uuid4().hex}.pdf"
    storage_root = Path(settings.local_storage_path).resolve()
    target = storage_root / relative_key
    size_bytes, digest = await _stream_pdf_to_storage(file, target)

    try:
        pending = PendingResumeUpload(
            organization_id=job.organization_id,
            job_id=job.id,
            storage_key=str(relative_key),
            original_filename=filename,
            mime_type="application/pdf",
            size_bytes=size_bytes,
            sha256=digest,
            uploaded_by=user.id,
        )
        db.add(pending)
        await db.flush()
        task = ProcessingTask(
            organization_id=job.organization_id,
            task_type="PROCESS_RESUME_UPLOAD",
            entity_type="PENDING_RESUME_UPLOAD",
            entity_id=pending.id,
            status="PENDING",
            progress=0,
            priority=50,
            input_hash=digest,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
    except Exception:
        await db.rollback()
        target.unlink(missing_ok=True)
        raise

    return ResumeUploadRead(
        task_id=task.id,
        filename=filename,
        status=task.status,
        match_rule="pending",
    )


@router.get("/{job_id}/candidates/{application_id}/resume")
async def get_candidate_resume(
    job_id: int,
    application_id: int,
    disposition: str = Query(default="inline", pattern="^(inline|attachment)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """Serve one resume only after verifying access to its job and application."""
    await get_job_or_404(job_id, db, user)
    application = await db.get(JobApplication, application_id)
    if application is None or application.job_id != job_id:
        raise HTTPException(status_code=404, detail="候选人不存在")

    resume = await db.get(ResumeFile, application.resume_file_id)
    if resume is None or resume.deleted_at is not None:
        raise HTTPException(status_code=404, detail="简历文件不存在")

    storage_root = Path(get_settings().local_storage_path).resolve()
    source = (storage_root / resume.storage_key).resolve()
    if storage_root not in source.parents or not source.is_file():
        raise HTTPException(status_code=404, detail="简历文件不存在")

    return FileResponse(
        source,
        media_type=resume.mime_type or "application/pdf",
        filename=resume.original_filename,
        content_disposition_type=disposition,
    )
