from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.candidates import router as candidates_router
from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.resumes import router as resumes_router
from app.api.setup import router as setup_router
from app.api.tasks import router as tasks_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(setup_router, prefix=settings.api_prefix)
app.include_router(jobs_router, prefix=settings.api_prefix)
app.include_router(resumes_router, prefix=settings.api_prefix)
app.include_router(tasks_router, prefix=settings.api_prefix)
app.include_router(candidates_router, prefix=settings.api_prefix)
app.include_router(evaluations_router, prefix=settings.api_prefix)
