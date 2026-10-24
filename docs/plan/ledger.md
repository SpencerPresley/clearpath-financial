# Orchestration ledger

Source of truth for what's in flight and what's done. Re-read this first after any context compaction.
Agent final reports live in `reports/<task>.md`; reviews in `reviews/<task>.md`.
Rulings use: `Ruling: <decision> — <why> — <cost if wrong>`.

## Status

| Task | Owner | Branch / PR | Status | Notes |
|---|---|---|---|---|
| scaffold | orchestrator | main `430486c` | done | backend, frontend, compose, CI, CLAUDE.md |
| infra-terraform | agent (worktree) | — | in progress | write + validate + plan only; apply deferred to deploy wave |
| sample-tracker | agent (worktree) | — | in progress | messy xlsx + generator + intended-mess README |
| spec | orchestrator | main | builder check running | docs/spec.md; builder-check questions go to reviews/spec-builder-check.md |

## Rulings

- Ruling: Terraform is written and planned now, applied at the deploy wave — avoids paying for NAT/RDS/WAF while nothing is deployable — cost if wrong: a later apply surfaces account-level issues (quotas, OIDC provider exists) later than ideal.
- Ruling: x86_64 EC2 (t3.medium) rather than Graviton — images build on standard GitHub-hosted runners without cross-compiling — cost if wrong: ~20% higher instance price for a short-lived demo.
