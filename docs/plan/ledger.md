# Orchestration ledger

Source of truth for what's in flight and what's done. Re-read this first after any context compaction.
Agent final reports live in `reports/<task>.md`; reviews in `reviews/<task>.md`.
Rulings use: `Ruling: <decision> — <why> — <cost if wrong>`.

## Status

| Task | Owner | Branch / PR | Status | Notes |
|---|---|---|---|---|
| scaffold | orchestrator | main `430486c` | done | backend, frontend, compose, CI, CLAUDE.md |
| shared domain vocabulary | orchestrator | main `44e7264` | done | backend/core/domain.py enums + offer-terms schemas; per-worktree test DB suffix |
| 0 foundation (#1) | agent (worktree `ws0/foundation`) | — | in progress | models, migrations, patterns, API contract |
| C rules engine (#4) | agent (worktree `wsC/rules-engine`) | — | in progress | pure engine in backend/checks/engine |
| H design system (#9, part 1) | agent (worktree `wsH/design-system`) | — | in progress | tokens, icon registry, components, shell, gallery |
| infra-terraform (#2) | agent (worktree) | PR #16 | fixing review | review: 1 blocker (immutable OIDC sub), 5 should-fix; app follow-ups in #18 |
| sample-tracker (#3) | agent (worktree) | PR #17 merged `b01999b` | done | 180 rows; samples/README.md is the import oracle; importer notes in reports/sample-tracker.md |
| spec | orchestrator | main `95871ce`+ | done; builder-check rulings in spec §4.2 | docs/spec.md; builder-check questions go to reviews/spec-builder-check.md |

## Rulings

- Ruling: Terraform is written and planned now, applied at the deploy wave (Spencer approved running `terraform apply` once the app is deployable) — avoids paying for NAT/RDS/WAF while nothing is deployable — cost if wrong: a later apply surfaces account-level issues (quotas, OIDC provider exists) later than ideal.
- Ruling: x86_64 EC2 (t3.medium) rather than Graviton — images build on standard GitHub-hosted runners without cross-compiling — cost if wrong: ~20% higher instance price for a short-lived demo.

## References for later workstreams

- **K (assistant):** query LangChain docs through the `docs-langchain` MCP (streaming, checkpointer, tools,
  human-in-the-loop middleware). LangChain also publishes frontend/UI docs and an example Next.js agent UI;
  use them for the chat panel, streaming, and interrupt (approve/edit/reject) UX, replicating where it fits
  our stack (React + TanStack, SSE). Verified so far: `HumanInTheLoopMiddleware` (requires a checkpointer),
  `langgraph-checkpoint-postgres` (`PostgresSaver`/`AsyncPostgresSaver`, call `.setup()` once),
  `GenericFakeChatModel` accepts `AIMessage`s with `tool_calls` for tests.
- **K runtime:** request-scoped SSE of `stream_events(version="v3")`, state only from the Postgres
  checkpointer (never rebuild history per request), thread ownership check, 15s SSE keepalive for CloudFront's
  60s origin timeout. Full notes on issue #11.
- **Long requests behind CloudFront:** anything that can exceed ~60s (import commit, evidence-pack export)
  runs as a Celery job with a status endpoint, not inline in the request.
- **Prompts/tools for D and K:** invoke the prompt-engineering and context-engineering skills.
- **UI work:** make-interfaces-feel-better skill; Playwright MCP or CLI for screenshots.

## Lessons

- Multi-step shell verification must use `set -e`; a failed edit script once let a commit with pyrefly
  errors through (fixed in `2f6681e`).
- Ruling: deploy role trusts `<immutable-repo-prefix>:ref:refs/heads/main`, not a GitHub environment — environments and branch protection aren't available for this private repo on the Free plan, so an environment pin would trust any branch declaring it — cost if wrong: anyone with push to main can deploy (true of the original design too).

## Questions for Spencer (blocking or decision-needed)

Resurface these when Spencer is back. Each has what I did meanwhile.

- (none yet)

## Orchestrator notes

- Before pulling the PR #16 merge: delete the untracked `docs/plan/reviews/infra-terraform.md` in main's
  working tree (the PR adds the same path).
