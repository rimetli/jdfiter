import os

os.environ.setdefault("APP_SECRET", "test-secret-with-at-least-32-characters")
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_DATABASE", "test")
os.environ.setdefault("MYSQL_USERNAME", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

