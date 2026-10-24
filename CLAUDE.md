# ClearPath Financial: marketing compliance review

Internal tool for a (fictional) nonbank consumer lender's compliance team. Marketing submits content
(ads, landing pages, emails, affiliate creatives); reviewers check it against regulations with automated
code checks plus LLM pre-review and record decisions. It replaces an Excel tracker + email workflow.

Start with `docs/spec.md` (intent, scope, UI and engineering standards, workstreams). Detail: `docs/product-spec.md` (workflow, data model, screens) and
`docs/decisions.md` (why, and what's deliberately out of scope). Regulatory substance with citations:
`docs/research/regulations.md`.

## Layout

```
backend/    Django + django-ninja API, Celery. See backend/CLAUDE.md
frontend/   Vite + React + TS SPA. See frontend/CLAUDE.md
docs/       spec, decisions, research
.github/    CI: backend-ci, frontend-ci, api-contract (schema/client drift), security (semgrep)
compose.yaml  local stack: db (pgvector pg17), redis, web, worker, beat
Makefile    every common command; `make help`
```

## Invariants (don't break these)

- The AI never approves. No model-facing tool or output can change an item's status; only a human
  decision does.
- Every state change goes through a service function that writes the state and an `Event` row in one
  transaction. Nothing updates or deletes events.
- Versions are immutable. Approvals reference an exact version plus the offer-terms versions it quotes.
- LLM findings are rejected unless their quote sits exactly at `[start, end)` in the version text.
- No raw dicts across boundaries: typed dataclasses / ninja schemas in and out of services and selectors.

## Environment

- The repo-root `.env` is a 1Password Environment mount (a named pipe). Read it, never write it.
  `.env.example` lists the keys. Set `CLEARPATH_ENV_FILE=""` to skip it (CI does).
- Compose publishes Postgres on 55432 and Redis on 56379 to avoid clashing with other local stacks.

## Workflow

Orchestration state: `docs/plan/ledger.md` (read it first after a context reset).

Errors: catch only where the code can decide what to do; domain errors are typed exceptions mapped to
HTTP once in the API's exception handlers (spec §6.1).

TDD: write the failing test first, at the lowest layer that can express it (pure function >
service with DB > API). `make check` runs what CI runs. After any API schema change run `make schema`
and commit `frontend/openapi/ninja.json` plus `frontend/src/api/generated`.
