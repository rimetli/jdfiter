from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.jobs import get_job_or_404
from app.core.auth import get_current_user
from app.db.models import JobApplication, ProcessingTask, ResumeFile, User
from app.db.session import get_db

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _get_task_for_user(task_id: int, db: AsyncSession, user: User) -> ProcessingTask:
    task = await db.get(ProcessingTask, task_id)
    if task is None or task.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    if user.role == "ADMIN":
        return task
    if task.entity_type == "JOB_APPLICATION":
        application = await db.get(JobApplication, task.entity_id)
        if application is not None:
            await get_job_or_404(application.job_id, db, user)
            return task
    if task.entity_type == "RESUME_FILE":
        resume = await db.get(ResumeFile, task.entity_id)
        if resume is not None and resume.uploaded_by == user.id:
            return task
    raise HTTPException(status_code=404, detail="任务不存在")


@router.get("/{task_id}")
async def get_task(
    task_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    task = await _get_task_for_user(task_id, db, user)
    return {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "progress": task.progress,
        "error_code": task.error_code,
        "error_message": task.error_message_safe,
    }


@router.post("/{task_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_task(
    task_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    task = await _get_task_for_user(task_id, db, user)
    if task.status != "FAILED":
        raise HTTPException(status_code=409, detail="仅失败任务可以重试")
    task.status = "PENDING"
    task.progress = 0
    task.error_code = None
    task.error_message_safe = None
    task.locked_by = None
    task.locked_at = None
    task.completed_at = None
    task.attempt_count = 0
    task.available_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return {"id": task.id, "status": task.status, "progress": task.progress}
