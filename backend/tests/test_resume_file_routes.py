import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_resume_preview_route_rejects_anonymous_requests() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/jobs/1/candidates/1/resume")
    assert response.status_code == 401
