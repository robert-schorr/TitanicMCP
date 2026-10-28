# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-install-project

COPY README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp

RUN groupadd --gid 10001 titanic \
    && useradd --uid 10001 --gid 10001 --no-create-home \
    --home-dir /app --shell /usr/sbin/nologin titanic \
    && mkdir -p /app/data \
    && chown titanic:titanic /app/data

WORKDIR /app

COPY --from=builder --chown=titanic:titanic /app/.venv /app/.venv
COPY --from=builder --chown=titanic:titanic /app/src /app/src

USER titanic

EXPOSE 8000

ENTRYPOINT ["titanic-mcp"]
