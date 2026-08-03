import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/api/v1/jobs/1/candidates", {}),
        ("POST", "/api/v1/jobs/1/evaluations/batch", {"json": {"application_ids": [1]}}),
        ("POST", "/api/v1/jobs/1/resumes", {"files": {"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}}),
        ("GET", "/api/v1/jobs/1/requirement-versions", {}),
        ("GET", "/api/v1/tasks/1", {}),
        ("POST", "/api/v1/tasks/1/retry", {}),
        ("GET", "/api/v1/evaluations/1", {}),
        ("POST", "/api/v1/evaluations/1/human-decision", {"json": {"decision": "HOLD"}}),
        ("DELETE", "/api/v1/jobs/1", {}),
    ],
)
async def test_sensitive_routes_reject_anonymous_requests(
    method: str, path: str, kwargs: dict
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.request(method, path, **kwargs)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_organization_enumeration_is_not_exposed() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/setup/organizations")
    assert response.status_code == 404
