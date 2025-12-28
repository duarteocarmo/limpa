# syntax=docker/dockerfile:1

FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy application code
COPY . .

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Collect static files
RUN uv run python manage.py collectstatic --noinput

# Create data directory for SQLite
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uv", "run", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
