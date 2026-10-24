# ClearPath Financial · Compliance Review

An internal tool that increases the throughput of a consumer lender's marketing compliance team by
replacing their Excel-tracker-and-email review process.

- What it is and why: [`docs/product-spec.md`](docs/product-spec.md), [`docs/decisions.md`](docs/decisions.md)

## Run it locally

Requirements: Docker, uv, Node 26.

```bash
# .env: add the keys from .env.example to the 1Password Environment that mounts it.
# Without 1Password: cp .env.example .env
make install                # backend + frontend deps
make up                     # Postgres, Redis, API on :8000, Celery worker + beat
make dev-web                # SPA on http://localhost:5173
make check                  # lint, format, types, migrations, tests
```

`make help` lists every target.
