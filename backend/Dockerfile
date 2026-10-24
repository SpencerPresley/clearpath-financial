# syntax=docker/dockerfile:1

# ---- deps: resolve the locked environment once, reuse in dev and prod ----
FROM ghcr.io/astral-sh/uv:0.13.5-python3.13-trixie-slim AS deps
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---- dev: adds test/lint/typecheck tools; source is bind-mounted by compose ----
FROM deps AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-groups --no-install-project
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY . .
EXPOSE 8000

# ---- prod: slim runtime, venv + source only, non-root ----
FROM python:3.13-slim-trixie AS prod
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.prod
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=deps --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
