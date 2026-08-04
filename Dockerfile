FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend-runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.tencent.com/pypi/simple \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5
WORKDIR /app/backend
RUN useradd --system --uid 10001 --create-home appuser
COPY backend/pyproject.toml ./
COPY backend/app/ ./app/
COPY backend/migrations/ ./migrations/
COPY backend/alembic.ini ./
RUN pip install .
USER appuser

FROM nginx:1.27-alpine AS frontend-runtime
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /build/frontend/dist/ /usr/share/nginx/html/
