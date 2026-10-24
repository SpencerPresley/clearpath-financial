.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE := docker compose
BACKEND := cd backend &&
FRONTEND := cd frontend &&
SEMGREP := semgrep@1.182.0

# Host-run backend commands talk to the compose services on their published ports.
# Process env beats the .env file in the typed settings, so this pins them regardless of .env.
HOST_SERVICES := POSTGRES_HOST=localhost POSTGRES_PORT=$(or $(POSTGRES_HOST_PORT),55432) \
	REDIS_URL=redis://localhost:$(or $(REDIS_HOST_PORT),56379)/0

.PHONY: help install up down logs ps build migrate makemigrations manage shell dev-web \
        test test-backend test-frontend test-browser test-e2e \
        lint lint-backend lint-frontend fmt fmt-check typecheck \
        migrations-check schema semgrep check

## help: list targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed -e 's/^## //' | awk -F': ' '{printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

## install: install backend (all groups) and frontend dependencies
install:
	$(BACKEND) uv sync --all-groups
	$(FRONTEND) npm ci

## up: start db, redis, web (uvicorn --reload), worker, beat
up:
	$(COMPOSE) up -d --build

## down: stop the stack
down:
	$(COMPOSE) down

## logs: follow logs (SERVICE=web to filter)
logs:
	$(COMPOSE) logs -f $(SERVICE)

## ps: show service status
ps:
	$(COMPOSE) ps

## build: build backend images
build:
	$(COMPOSE) build

## migrate: apply migrations in the web container
migrate:
	$(COMPOSE) exec web python manage.py migrate

## makemigrations: create migrations in the web container (ARGS="app_label")
makemigrations:
	$(COMPOSE) exec web python manage.py makemigrations $(ARGS)

## manage: run a manage.py command in the web container (ARGS="...")
manage:
	$(COMPOSE) exec web python manage.py $(ARGS)

## shell: Django shell in the web container
shell:
	$(COMPOSE) exec web python manage.py shell

## dev-web: run the Vite dev server on :5173 (proxies /api and /_allauth to :8000)
dev-web:
	$(FRONTEND) npm run dev

## test: backend + frontend unit tests (needs `make up` for Postgres)
test: test-backend test-frontend

## test-backend: pytest against the compose Postgres on localhost:55432
test-backend:
	$(BACKEND) $(HOST_SERVICES) uv run pytest -q

## test-frontend: Vitest unit lane
test-frontend:
	$(FRONTEND) npm run test:run

## test-browser: Vitest browser lane (real Chromium)
test-browser:
	$(FRONTEND) npm run test:browser

## test-e2e: Playwright e2e against a production build
test-e2e:
	$(FRONTEND) npm run test:e2e

## lint: ruff + eslint
lint: lint-backend lint-frontend

lint-backend:
	$(BACKEND) uv run --group lint ruff check .

lint-frontend:
	$(FRONTEND) npm run lint

## fmt: format backend and frontend
fmt:
	$(BACKEND) uv run --group lint ruff format . && uv run --group lint ruff check --fix .
	$(FRONTEND) npm run format

## fmt-check: check formatting without writing
fmt-check:
	$(BACKEND) uv run --group lint ruff format --check .
	$(FRONTEND) npm run format:check

## typecheck: pyrefly + tsc
typecheck:
	$(BACKEND) uv run --group typecheck pyrefly check
	$(FRONTEND) npm run typecheck

## migrations-check: fail if models have changes without migrations
migrations-check:
	$(BACKEND) $(HOST_SERVICES) uv run python manage.py makemigrations --check --dry-run

## schema: export the OpenAPI schema and regenerate the frontend client
schema:
	$(BACKEND) uv run python manage.py export_openapi_schema --api config.api.api \
		--output ../frontend/openapi/ninja.json --indent 2 --sorted
	$(FRONTEND) npm run generate:api

## semgrep: security scan (pinned, isolated from the project lock)
semgrep:
	uvx $(SEMGREP) scan --error --metrics=off \
		--config p/python --config p/django --config p/typescript --config p/react \
		--config p/secrets --config p/github-actions \
		backend frontend/src .github

## check: everything CI runs, locally
check: lint fmt-check typecheck migrations-check test
