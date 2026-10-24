# Orchestration ledger

Source of truth for what's in flight and what's done. Re-read this first after any context compaction.
Agent final reports live in `reports/<task>.md`; reviews in `reviews/<task>.md`.
Rulings use: `Ruling: <decision> — <why> — <cost if wrong>`.

## Status

| Task | Owner | Branch / PR | Status | Notes |
|---|---|---|---|---|
| scaffold | orchestrator | main `430486c` | done | backend, frontend, compose, CI, CLAUDE.md |
| shared domain vocabulary | orchestrator | main `44e7264` | done | backend/core/domain.py enums + offer-terms schemas; per-worktree test DB suffix |
| 0 foundation (#1) | agent (worktree) | PR #22 merged `1da02c7` | done | 296 tests; Interfaces in reports/foundation.md; dev DBs recreated (custom user model) |
| C rules engine (#4) | agent (worktree) | PR #21 merged | done | 42 code rules + 4 human items; 326 tests; ENGINE_VERSION in cache keys; ~3 ms per 5 KB ad |
| D llm core (#5, phase 1) | agent (worktree) | PR #23 merged `f126747` | done | 7 LLM rules; live eval: recall 100%, precision 72%, 0/5 clean FPs, injection resisted, $0.00025/review (reports/llm-core-live-eval.md) |
| E review workflow (#6, +#18) | agent (worktree) | PR #25 merged `d0fffbd` | done | 1201 backend tests; reviewer found 2 critical (carry-forward resurrecting reversed dismissals; approve with accepted findings), fixed |
| E follow-up: evidence re-check | agent (resumed E) | PR #26 merged | done | adds checks migration 0003 (system dismissal) |
| D2 llm wiring (#5) | agent (worktree `wsD/llm-wiring`) | — | in progress | outbox handler → task → findings; failed/skipped/retry; stuck-running reconciliation. Unblocks Approve |
| F offer terms (#7) | agent (worktree `wsF/offer-terms`) | — | in progress | publish, impact preview, per-item fan-out, fast-track (single + bulk) |
| G import/export (#8) | agent (worktree) | PR #24 merged | done | sample imports to exact oracle totals (178 items); xlsx export with formula-injection guard; evidence pack zip + sha256 manifest |
| H2 queue (#9, part 2) | agent (worktree `wsH/queue`) | — | in progress | table, filters, saved views, board, drawer, /api/me wiring |
| I review + intake (#10) | agent (worktree) | PR #27 merged `08308a4` | done | UI review: 1 blocker + 11 should-fix, 17 fixed; UTF-16 span conversion tested |
| I follow-ups | agent (resumed I) | PR #28 merged | done | re-review actions by reopen reason; fetch-URL removed; Pull = EyeSlash |
| H design system (#9, part 1) | agent (worktree) | PR #19 merged | done | 145 unit tests; contrast-tested tokens; 55-key icon registry; follow-ups in #20 |
| infra-terraform (#2) | agent (worktree) | PR #16 merged `b7c2ea3` | done (not applied) | 74 resources; sub verified from a real token; app follow-ups in #18 |
| sample-tracker (#3) | agent (worktree) | PR #17 merged `b01999b` | done | 180 rows; samples/README.md is the import oracle; importer notes in reports/sample-tracker.md |
| spec | orchestrator | main `95871ce`+ | done; builder-check rulings in spec §4.2 | docs/spec.md; builder-check questions go to reviews/spec-builder-check.md |

## Rulings

- Ruling: AI (llm) findings are always severity=warning, enforced at persistence — the AI never blocks or approves on its own judgment; blocking belongs to deterministic checks and the human — cost if wrong: a real AI catch needs the reviewer to accept it (which then blocks approve anyway).
- Ruling: Reaffirm is not offered on terms_changed re-reviews — the old version quotes superseded terms and reaffirm re-runs code checks against current terms — Fast-track or the normal lane instead.
- Ruling: controls whose endpoint returns 501 don't ship (fetch-URL removed from intake until M builds it).

- Ruling: attaching evidence to an item in a reviewable status re-runs code checks on the current version; open findings whose rule no longer fires are dismissed by the system with reason "Resolved: <kind> attached"; accepted/human-dismissed findings untouched — keeps attachment-kind rules honest without making the reviewer re-triage — cost if wrong: system dismissals to reverse.
- Ruling: reviewer-edit versions carry vN's AI result (no re-run); human checklist dismissals carry only into reviewer-edit and fast-track versions (E's calls, accepted).

- Ruling: import/export/evidence jobs enqueue on transaction commit (`transaction.on_commit`), not through the outbox — the events record results, not requests, and the jobs are idempotent — cost if wrong: a job lost if the process dies between commit and enqueue; user retries. Exception noted against backend/CLAUDE.md.
- Ruling: legacy items are excluded from the default queue and queue stats — an imported open tracker row has no version to review — cost if wrong: none; `is_legacy` filter still finds them.
- Ruling: imported approvals have no Decision row; evidence pack for a legacy item returns 409 with a plain explanation — a decision needs a version and legacy items are metadata-only (ruling 7).

- Ruling: attachment reads — partner attachments (agreements) readable by reviewer/lead/admin, not marketers; item, version, and decision evidence readable by anyone who can read the item — reviewers check affiliate copy against the agreement — cost if wrong: one permission check to tighten. Owner: E.
- Ruling: library has two views — "Approved to run" (current status approved; default) and precedent search across every version that ever received an approval decision, showing its current status as a badge — precedent value doesn't lapse, run-permission does — cost if wrong: a filter default. Owner: E (selector) + J (UI).
- Ruling: E owns wiring C's engine into `checks.services.run_code_checks` and the `/checks/preview` endpoint (live as-you-type); J owns metrics endpoints + page; K revises the assistant stub contract to whatever useStream needs (#11).

- Ruling: prescreen notices are checked twice — a blocking code check that the notice text is present, plus a human checklist item for layout — presence is text-checkable, layout isn't — cost if wrong: one extra triage click on prescreen items.
- Ruling: "pre-approved" invitations on mortgage_prequal items are a warning — ClearPath offers prequalification, a materially different product — cost if wrong: occasional warning to dismiss.
- Ruling: check-result caches key on ENGINE_VERSION as well as RULESET_VERSION — a regex fix must invalidate cached findings even when the law hasn't changed — cost if wrong: none.

- Ruling: no warm brand accent; navy is the only brand color — spec §5.2 already uses every warm hue for a status, and the UI reviewer read a gold mark as "warning" — cost if wrong: a slightly plainer brand; easy to add a non-status accent later.

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

- (none open)


## Orchestrator notes

- Backend gaps from I (bundle into next backend follow-up): ItemRowOut lacks latest decision reason and approval_expires_at (/mine does N fetches; Approved shows no expiry); SubmitItemIn takes no attachments (evidence uploads after create; E's re-check PR #26 now resolves attachment findings on upload); single-item fast-track endpoint (F); shell Viewer from /api/me (H2).

- Deploy wave checklist: set FRONTEND_BASE_URL to the CloudFront domain (admin login redirects there); settings for DOCUMENTS_BUCKET (S3 storage) and CloudFront-Viewer-Address as allauth client IP header (from #18 comments).

- G follow-ups for J/later: stale running jobs if the worker dies (no redelivery), old export files never deleted, Request-ID reuse across files is skipped as duplicate.

- Next after merges: F offer terms (after E), D phase 2 wiring (after E; note: engine `rule.py` `to_finding` labels every non-code rule HUMAN, so phase 2 must build LLM findings itself or fix that; offsets are Python str indices, frontend I must convert to UTF-16), J secondary screens + metrics, K assistant (useStream spike first; revise the Foundation assistant stub contract), L demo seed, then deploy wave (terraform apply approved), then full UI walkthrough per role.

- Resolved: the backend's typed settings read the 1Password-mounted `.env` non-interactively (verified by
  printing only a has-key boolean). The orchestrator runs the live LLM eval after the LLM-core PR merges;
  it would only block if 1Password is locked.
