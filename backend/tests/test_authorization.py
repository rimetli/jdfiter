import pytest
from fastapi import HTTPException

from app.api.jobs import get_job_or_404
from app.db.models import JobPosition, User


class FakeDB:
    def __init__(self, job: JobPosition | None):
        self.job = job

    async def get(self, model, identifier):
        return self.job if model is JobPosition and self.job and self.job.id == identifier else None


def make_user(user_id: int, role: str = "USER", organization_id: int = 1) -> User:
    return User(
        id=user_id,
        organization_id=organization_id,
        email_ciphertext=f"u{user_id}@example.com",
        email_hash=str(user_id),
        display_name=f"user-{user_id}",
        role=role,
        status="ACTIVE",
    )


def make_job(created_by: int) -> JobPosition:
    return JobPosition(
        id=10,
        organization_id=1,
        name="Agent 工程师",
        jd_content="招聘一位有 Agent 经验的工程师",
        status="DRAFT",
        created_by=created_by,
    )


@pytest.mark.asyncio
async def test_regular_user_cannot_access_another_users_job() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_job_or_404(10, FakeDB(make_job(created_by=2)), make_user(1))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_access_any_job_in_organization() -> None:
    job = await get_job_or_404(10, FakeDB(make_job(created_by=2)), make_user(1, "ADMIN"))
    assert job.id == 10
