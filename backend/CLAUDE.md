# Backend

Django 6 + django-ninja, Postgres 17 (pgvector image), Celery + Redis, django-allauth (headless, MFA).
Python 3.13, uv. Lint/format: ruff. Types: pyrefly with django-stubs.

## Layout

```
config/            settings (base/dev/test/prod), urls, asgi, celery, api.py (the NinjaAPI)
<domain app>/      one Django app per domain: reviews, checks, terms, partners, audit, imports, exports, assistant
  models.py        persistence only; no business rules
  services.py      the ONLY place state changes. One function per user action; validates the transition,
                   writes rows + an Event in one transaction
  selectors.py     reads. Return typed dataclasses, not querysets or dicts, across the boundary
  api.py           thin ninja router: parse -> call service/selector -> return schema
  schemas.py       ninja Schemas for the API
  tasks.py         Celery tasks (enqueued by the outbox dispatcher, not directly from services)
  tests/
core/              cross-cutting: health, Postgres extensions migration
```

## Conventions

- Settings read the environment only through `Env` in `config/settings/base.py` (typed, fails fast).
- Auth: session cookie via `django_auth` (CSRF enforced on unsafe methods). Public endpoints opt out
  with `auth=None` explicitly.
- Every operation sets `operation_id` and a router tag; they become generated hook names in the frontend.
- Postgres features are fair game (EXCLUDE constraints, GIN/trigram, advisory locks). Tests run on real
  Postgres, never SQLite.
- Type everything. Pyrefly is loose on `.annotate()`/`.values()`; convert those results to dataclasses
  inside the selector.

## Commands (from repo root unless noted)

| Command | What |
|---|---|
| `make up` / `make down` | compose stack (web on :8000, migrations run on start) |
| `make test-backend` | pytest (needs Postgres from `make up`) |
| `make lint-backend`, `make typecheck`, `make fmt` | ruff / pyrefly / format |
| `make migrations-check` | fail on model changes without migrations |
| `make makemigrations ARGS=app` | create migrations in the container |
| `make schema` | export OpenAPI to `frontend/openapi/ninja.json` and regenerate the client |
