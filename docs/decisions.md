# Decisions

What we've settled, why, and what each alternative would have cost. Open questions are at the bottom.

## Problem framing

**We're building a marketing compliance review tool, not an affiliate CRM.**
The brief says: "The compliance marketing team's **review process** ... currently done via Excel and email ... is bottlenecking growth." At a consumer lender, that team approves marketing content (ads, landing pages, emails, SMS, social posts, affiliate creatives) before it ships.
- **Excel** is the review tracker.
- **Email** carries drafts in, redlines out, and approvals buried in threads.
- **Affiliates matter** because the lender is liable for their copy, not because the team manages the relationships. Reg Z comment 2(a)(2)-2 says "All persons must comply with the advertising provisions." CFPB Supervisory Highlights Issue 37 (2024) found lenders deceptive over partner ads because "the lenders exercised control and approval rights over these advertisements." See `research/regulations.md` §1 and §8.

**Where the throughput goes today**, which is the brief's stated goal:
1. Nobody can see the queue, so marketers ask for status and reviewers stop to answer.
2. Versions get mixed up across email attachments.
3. Claims that were already approved are reviewed from scratch, because there's no searchable record of past decisions.
4. Proving who approved which version means reconstructing it from inboxes.

**Rejected:** affiliate CRM, outreach and deal management, calendar integration. They belong to the partnerships team and don't touch the review bottleneck.

## Company facts (fictional, chosen for consistency)

| Fact | Choice | Why / consequence |
|---|---|---|
| Bank or nonbank | **Nonbank** | "National consumer finance company" reads as nonbank. Reg N (12 CFR 1014) applies, and so does CFPB supervision. There's no federal Equal Housing logo requirement for nonbank ads: HUD's 24 CFR 109 was removed in 1996, and FDIC 12 CFR 338.3 covers only FDIC-supervised banks. |
| Credit cards | **Issued through a sponsor bank** | This is how nonbanks offer general-purpose cards. Example: Mission Lane's Visa "is issued by Transportation Alliance Bank… or WebBank," and "Mission Lane LLC… is not a bank" ([missionlane.com/legal](https://www.missionlane.com/legal)). Card ads carry an issuer line. That's a good code check, but its *legal* basis is unverified and it may only be practice. The sponsor bank probably wants to sign off on card marketing; that's judgment, written up but not built. |
| States | **California** | PromptArmor is in SF. Cal. Fin. Code §22162 (verified): a licensee "shall not place an advertisement disseminated primarily in this state for a loan unless the licensee discloses in the printed text… the license under which the loan would be made or arranged." The statute prescribes no wording, so the check accepts a configurable list of phrases. California mortgage NMLS-in-ad rules are **unverified**. |
| FHA-approved | **No** | Any ad implying government backing is blocked outright under Reg Z 1026.24(i)(3) and Reg N 1014.3. HUD Handbook 4000.1 stays out of scope. |

**More states:** the code is reusable (a `Rule` row with `jurisdiction`, matched against `ReviewItem.markets[]`). The cost per state is legal research, usually one to three rule rows, each needing a primary source.

## Delivery

**Hosted web app with role-based demo logins** (Marketer, Reviewer, Compliance Lead, Admin). Production would use SSO.
- **Rejected: a Tauri or Electron desktop app.** The workflow involves several parties, so the data has to live on a shared backend anyway; a desktop shell doesn't make it private. It also adds code signing and packaging, and asks evaluators to install an unsigned binary. For an internal tool, security means authentication, roles, and an append-only audit log.
- **Scalability isn't a goal** (one internal team). **Auditability is.**

**Demo data:**
- Commit `samples/clearpath_review_tracker.xlsx` to the repo. It's realistically messy:
  - inconsistent status values ("Approved w/ changes" vs "Approved - minor edits")
  - multi-round comments in one cell
  - blank expiries and mixed date formats
- Pre-seed the hosted database with it.
- The Import page has a "Load sample tracker" button so evaluators don't need the file, plus a "Reset demo" button.

## Scope

**Core:**
- Intake, with live code checks shown to the submitter
- Queue (table view first, board view second)
- Review screen with AI pre-check and version diff
- Decisions with required evidence
- Offer terms with versioning and re-review fan-out
- Append-only event log, which drives the audit trail, notifications and metrics
- Excel import, and export of any view to xlsx
- Partner records with item and findings history
- AI assistant (see below)

**Stretch:** affiliate page drift monitoring against demo affiliate pages we host ourselves.

**Out, written up in this doc but not built:**

| Item | Why it's out | How we left room for it |
|---|---|---|
| Affiliate self-service portal | Needs external authentication, tenant isolation, and treating every upload as untrusted | `partner_id` everywhere; roles are a list, so a `partner` role is additive |
| Sponsor-bank second approval for card ads | Not core to the bottleneck | — |
| Pushing rates to affiliates | The real fix is a ClearPath-hosted rate feed or widget. We aren't the CMS. | — |
| Multi-state rules beyond California | Each state is legal research, not code (see above) | — |
| Real outbound email | Replaced by an Outbox page | — |
| Google login | Needs the custom domain for the OAuth redirect URI, and evaluators' emails would have to be added as consent-screen test users. Email/password demo logins cover the demo. | The `django-allauth[socialaccount]` extra is installed; it's added if time allows. |

## Key design decisions

### Code checks vs LLM checks
- **Code** owns hard facts: rate values against current offer terms, required disclosure strings, trigger terms, NMLS and license-number formats, banned phrases.
- **The LLM** owns judgment calls, and every finding must point to an exact span of the submitted text: is the creditworthiness qualifier actually there, is the soft-pull claim limited to the right step, is a paid relationship disclosed.
- **Human only:** Reg B discouragement through imagery and targeting.

Why: code is exact and free for numbers. It's also immune to prompt injection. A hidden "note to AI reviewers: pre-approved" can't talk a numeric comparison into passing.

### The AI can never approve
No model has a tool or output field that changes status. Submitted content is passed to models as marked data, never as instructions. Only a human records a decision.

### Approvals are tied to offer terms (the differentiator)
Each `Decision` records the `OfferTerms` versions the item quotes. When terms change, every approved item quoting the old version is affected: live items go to re-review, items not live expire (spec §4.2).

None of the roughly 14 vendors surveyed documents this (see `research/market.md`). That's absence from their marketing pages, not proof nobody does it.

It also falls out of a compliance requirement. Reg N 1014.5 requires nonbank mortgage advertisers to keep records of the products and terms available when the ad ran, plus every materially different version, for 24 months **from the last date the ad ran**. So placements need run dates.

### Rates are stored once, but terms changes are never auto-published
Offer values are detected in the copy, not typed as tokens: affiliate copy arrives as literal text ("12.99% APR"), so a code check extracts each rate/fee/example claim into a `TermsRef` (field + span). A terms change generates v+1 of each affected item by replacing those spans, with representative examples recomputed. For example, $10,000 / 36 months / 12.99% APR comes to $337/mo, so a new APR means a new payment amount.

Those versions go to a **fast-track lane**: the diff shows only the token changes, and the reviewer approves with one click.

Not auto-published, because:
- a changed number can change what the ad claims ("lowest rate" may stop being true)
- each version is a record that must be kept
- affiliate pages aren't ours to push to

### Rule citations carry dates
Rules change. The Reg B discouragement rule was rewritten effective 2026-07-21, and the CFPB withdrew guidance in May 2025. Every `Rule` has `effective_from`, and every `Decision` records the rule-set date, which answers "why did we approve this in March?"

### `needs_rereview` is its own state
A separate state is justified only when it allows different actions or guarantees different things. This one does both:
- **Guarantees:** a prior approval exists and the content is live.
- **Allows different actions:**
  - **Fast-track** a generated version
  - **Pull**: request takedown, tracked until confirmed down
  - **Reaffirm**: re-approve the same version with no resubmission
- **Separate metric:** time to fix live content is different from time to first review.
- **Higher priority:** something non-compliant is running now.

Approvals that expire with no active placement lapse to `expired` instead, because nothing is at risk.

### Approve-with-changes means the reviewer makes the edits
The reviewer's edits create v+1 authored by the reviewer, and that's the version approved. This keeps the rule "the approved version is exactly what goes live." Today it means "trust the marketer to apply the edits."

### Two kinds of file
- **The item under review** (copy, mailer PDF, mockup) lives in `Version`. It's never an email attachment.
- **Supporting evidence** is attached to an item, version, partner or decision. Examples: substantiation memos, rate sheets, prescreen criteria (Reg B 1002.12(b)(7) requires 25 months, FCRA 1681m(d)(3) requires 3 years), affiliate agreements, live screenshots.
- Attachments are immutable with a hash, and "replace" adds a new row.
- A `Decision` records which evidence it relied on, by hash. That's what goes into the export.

### Assistant: LangChain with human approval before sending
- **Read tools:** search items, get an item, search precedents, queue stats, offer terms, build an export.
- **One write tool:** `send_email`.
- **Recipient allowlist (`@clearpath`) enforced in the tool's code,** not the prompt. The assistant reads affiliate content, so injected text could try to email data to an outsider; that's the indirect-injection exfiltration path PromptArmor researches.
- **`send_email` always pauses** for approve / edit / reject via LangChain v1 `HumanInTheLoopMiddleware` (requires a checkpointer; [docs](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)).
- **Export files are built by app code from a filter.** The model chooses which report; it never writes the file contents.
- **The demo sends to an Outbox page,** not real mail.
  - `send_email` builds a real message with Django's `EmailMultiAlternatives`: a plain-text body plus an HTML
    body from Django templates.
  - A custom `EMAIL_BACKEND` writes the message to an `OutboxEmail` table. The Outbox page renders the HTML in
    a sandboxed iframe, showing who approved the send and when.
  - The allowlist and the human approval are enforced before the email layer, so they hold whichever backend
    is configured.
  - Real delivery (`django-anymail` with SES or Resend) is a settings change plus DNS (SPF/DKIM). It isn't
    worth it for the demo: the recipients are fictional `@clearpath` addresses, and loosening the allowlist so
    evaluators could receive mail would reopen the exfiltration path the allowlist exists to close.
- **LangChain over the Claude Agent SDK:** the Agent SDK is built for Claude-Code-style agents with filesystem and shell tools. That's more than an in-app assistant with about 7 custom tools needs, and we know LangChain. The model is Claude, through the Anthropic integration.

### Ergonomics: don't lose to the spreadsheet
Friction only where compliance requires it, which means only at the decision.
- The queue is a dense table: every column sortable and filterable, column chooser, saved views.
- Low-stakes fields (assignee, tags, notes) are edited inline; risk tier by reviewers and leads, with an event.
- Bulk assign and bulk fast-track approval.
- **Export any view to xlsx.** Don't compete with Excel on analysis.
- The decision form is prefilled from accepted findings and the item's attachments.

**Reviewer's main task, today:** open the email → open the attachment → mark up the PDF → reply → switch to Excel → find the row → update it. That's 3 apps, and the row update is easy to forget.

**In the tool:** open the item → accept or dismiss the pre-flagged spans → Approve. The row, notification and audit entry happen automatically.

### Queue views
- **Table by default.** It's what Excel users expect, and it handles volume.
- **Kanban board as a toggle,** for leads ("where's the bottleneck?") and marketers ("where's my stuff?").
- On the board, drag only where the move is ungated: Submitted → In review ("claim"). Dragging onto a gated state like Approved with open findings would fail or pop a form, which feels broken.
- The board's "Approved" column shows the last 14 days only.

### Metrics come from the event log
Time-in-queue and time-per-round are queries over the events, and the imported tracker's dates supply real history, so there's no placeholder data. They're built into the data model early and surfaced late, as a stats strip and an age column.

### Drift monitor
- **The checker identifies itself honestly** (`ClearPathComplianceBot/1.0`), not as a browser. Copy hidden by a stylesheet counts as visible: the check reads the page's text, not its rendering. Cloaking (serving the bot different content than people see) is out of scope for text-level checks; catching it would take browser-like fetching from unattributed addresses, which is a different product.
- **Approved copy intact, partner text beside it = unchanged.** The item doesn't reopen, but new blocking findings on the page (rules that don't fire on the approved copy) notify the assignee and the active leads in-app, once per new set of rules, and the placement shows an attention state on the review screen. That added text is exactly the risk, so it can't be silent.
- **One failed check is a failed check, three in a row is missing copy.** A 404/410 or an outage is a failed check (a moved URL or a bad hour shouldn't reopen anything), but 3 consecutive daily checks that couldn't fetch the page on a live placement reopen the item (drift_detected) with the failed checks linked. A failed manual Check now is recorded and shown but neither counts nor resets the streak, so a partner outage plus impatient clicking can't reopen the item. A success ends the streak, and so does a failure on our side (a stuck worker, an internal error): it says nothing about the page.
- **Reaffirm after drift only once the copy is back.** A drift_detected re-review offers Reaffirm only when the placement's latest check found the approved copy unchanged (the partner restored it); otherwise Check now or Pull. The reaffirm service enforces the same rule (409 `drift_not_restored`).

## Workflow policies

### Approval expiry
No regulation sets how long an approval lasts. It's company policy, stored in an editable `ExpiryPolicy(channel, months)` table. Rate changes are already handled by the link between approvals and offer terms, so expiry only has to catch everything else: rule changes, and content nobody has touched.

| Channel | Default | Why |
|---|---|---|
| One-off sends (email, SMS, direct mail drop) | End of the planned send window | The approval covers one send |
| Evergreen owned (site pages, templates, call scripts) | 12 months | A yearly pass catches rule changes on content nobody edits |
| Affiliate / partner placements, paid social | 6 months | The content sits outside our control and drifts |

### Reviewer assignment: automatic, with claiming still allowed

Each item is assigned by the first rule that applies:
1. A resubmission or re-review goes back to the previous reviewer.
2. Otherwise, it goes to the available reviewer with the lowest weighted open load (risk tier: high 3, medium 2, low 1). Ties go to whoever has gone longest without a new assignment.
3. If nobody is eligible, the item goes to the unassigned pool and the lead is notified.

Other rules:
- **No per-user cap.** Load only ranks reviewers.
- **Manual and bulk assignment by a lead skips automatic assignment.**
- **Who can reassign:**
  - leads and admins: anything, including in bulk
  - reviewers: claim from the pool, or hand off their own items
  - marketers: nothing
- **Every assignment event records its reason**, e.g. "Dana: load 4 vs Sam 7".

**Concurrency.** Assignment runs inside the submit transaction, under `pg_advisory_xact_lock(<ASSIGNMENT_KEY>)`. Load is computed after the lock is acquired. Under READ COMMITTED each statement gets a fresh snapshot, so the count sees the assignment the previous transaction just committed.
- **Rejected: `SKIP LOCKED`.** It picks from a partial set. Dana is skipped and Sam gets the item at load 10 vs her 5. If every row is locked, the set is empty and the item lands in the pool for no reason.
- **Rejected: row-level `FOR UPDATE`.** It works, but a lock on one advisory key can't deadlock on lock ordering.

**Reviewer specialties are rejected.** They'd need a category list, someone to own it, and per-reviewer membership, which multiplies the conditionals. If they're ever wanted, `product` already exists on every item, so it would be one reviewer-to-products table.

## Technical architecture

### Data
- **Postgres only.** Specific needs:
  - transactions spanning decision + status + event
  - a trigger that makes `event` append-only
  - `EXCLUDE USING gist (product WITH =, effective_range WITH &&)` so exactly one terms version is in effect at any time
  - a full-text `tsvector` generated column with a GIN index, plus `pg_trgm`
  - JSONB for event payloads, fees, and saved views
  - the LangGraph checkpointer (`langgraph-checkpoint-postgres`)
- **Rejected: NoSQL.** JSONB already covers flexible payloads, and we'd lose joins, transactions spanning several rows, and constraints.
- **State tables plus events, not event sourcing.** Each action is one service function that checks the transition, updates rows, and inserts the event in one transaction. Event sourcing would cost projections, replay, and versioning of event schemas, and nothing we need requires it.
- **The event log doubles as the transactional outbox.** A dispatcher polls `event WHERE id > cursor` and enqueues side effects. If Redis goes down after a commit, nothing is lost, so Redis is disposable.
- **Keys.** The primary key is a `bigint` identity. `CP-1042` is a display format derived from it. Imported Request IDs go in a separate unique `legacy_ref`.
- **One `ItemFilter` schema** is shared by the queue API, saved views, export, and the assistant's tools.
- **Indexes** are listed in `product-spec.md`. Proven with `EXPLAIN ANALYZE` against 50k seeded items. Most of the speed comes from avoiding N+1 queries, denormalized counts, and keyset pagination.

### Search
Lexical first:
- `find_phrase` uses `ILIKE` / similarity backed by a trigram GIN index.
- `search_text` uses `websearch_to_tsquery` with `ts_rank_cd`.

`ts_rank_cd` isn't BM25, and BM25 isn't available to us: ParadeDB `pg_search` isn't in the RDS extension list. That's fine at our corpus size.

Search returns ranked candidates, so a semantic channel can be fused in later with reciprocal rank fusion: pgvector 0.8.2 is on RDS for PG17. The case lexical search misses is paraphrase ("doesn't impact your credit" vs "won't hurt your score").

### Checks
- Code rules are pure functions.
- LLM findings are rejected unless the quote sits exactly at `[start, end)` in the version text.
- Tests:
  - the span validator is a pure function, so most cases need no model
  - `GenericFakeChatModel` (which emits `AIMessage` with `tool_calls`) feeds bad spans through the full path
  - each rule-check row in the regs report becomes should-flag / shouldn't-flag fixtures

### Stack
- **Backend:**
  - Django + django-ninja, with OpenAPI generating `ninja.json`
  - Celery + Redis on the same server
  - ASGI server, with SSE for assistant streaming
  - **no Channels**: live queue updates come from React Query refetch-on-focus plus polling
  - django-allauth in headless mode, with MFA
  - uv + `pyproject.toml`; ruff; Pyrefly with django-stubs, with selectors returning typed dataclasses to cover Pyrefly's loose `annotate`/`values` typing
  - pytest
- **Frontend:**
  - Vite + React + TypeScript
  - Orval generating React Query hooks, zod schemas, and MSW handlers. CI fails if the regenerated spec or client differs from what's committed.
  - TanStack Router (filters live in validated URL search params), Query, Table, Form, Charts, Markdown
  - Tailwind v4 with tokens in one `@theme` file; the default palette is reset so only ClearPath tokens compile
  - daisyUI with a custom theme
  - React Aria Components for menus, comboboxes, popovers, and dialogs
  - ESLint (type-aware `no-floating-promises`) + Prettier + `tsc --noEmit`
  - Vitest / Testing Library / MSW / Playwright
- **Rejected: the MUI Data Grid.** Column resizing *is* free, but multi-sort and multi-filter are Pro, and it brings a second styling system (Emotion). We sort and filter server-side anyway, so the deciding factor was one styling system.
- **Layout:**
  - backend: one Django app per domain, each with `models` / `services` (the only place state changes) / `selectors` / `api` / `schemas` / `tasks`
  - frontend: `src/features/*`, `src/api` (generated), `src/ui`, `src/theme`

### Hosting (AWS, Terraform)
- **One CloudFront distribution:**
  - the default path goes to the S3 frontend bucket, readable only by CloudFront
  - `/api/*` and `/_allauth/*` go to the app server, so session cookies and CSRF are same-origin and there's no CORS
  - SPA deep links are handled by a CloudFront Function on the S3 behavior only. Custom error responses apply to the whole distribution, so they would turn API 404s into `index.html`.
- **App server:** EC2 in a private subnet with no public IP, reached through a **CloudFront VPC origin**.
  - Outbound traffic (Anthropic API, image pulls) goes through a NAT gateway.
  - Docker Compose on the server runs web, Celery worker and beat, Redis, and the outbox dispatcher. Postgres runs on RDS instead.
- **Database:** RDS Postgres in private subnets, encrypted, accepting connections only from the app's security group.
- **Edge security:** CloudFront geo restriction to the US, plus AWS WAF:
  - managed rule sets: Common, KnownBadInputs, IP reputation
  - a rate-based rule on login
- **Server security:**
  - no port 22; shell and deploys go through SSM
  - IMDSv2 required, with a hop limit of 2. **Tradeoff:** the containers sit one Docker-bridge hop from the
    instance, and they need the instance role (SSM parameters, the documents bucket), so the hop limit can't
    be 1. That means an SSRF in Django could reach the role's credentials. IMDSv2's PUT-for-token step blunts
    the common GET-only SSRF. The alternative, handing credentials only to the web and worker containers,
    costs extra secret plumbing for one demo server.
  - secrets in SSM Parameter Store
  - documents bucket private, encrypted and versioned. Downloads stream through Django's permission-checked endpoints; the bucket is never exposed. **Rejected: presigned URLs.** A presigned URL is a bearer link: it keeps working for its lifetime after the user is deactivated or loses access, and it can leak through history, logs or a forwarded link. It would also put a second origin (S3) in the browser outside WAF and the geo restriction, and the SPA would need to change. The cost of streaming is that file bytes pass through the app server and NAT, which is negligible at demo file sizes.
  - the app's role can read and write documents but not delete them (nothing in the app deletes a stored file)
  - allauth rate limits key on `CloudFront-Viewer-Address`, which is trustworthy only because the origin is reachable solely through the CloudFront VPC origin
- **Deploy:**
  1. GitHub-hosted runners build the images and push them to ECR.
  2. The deploy job (the only job with `id-token: write`, running after credential-free build jobs) assumes an IAM role via GitHub OIDC. The trust policy pins `aud` and `sub = repo:SpencerPresley@153392395/clearpath-financial@1431827457:ref:refs/heads/main` (GitHub's immutable subject format, observed from a real token). It's not pinned to a GitHub environment, because environments and branch protection aren't available on this private Free-plan repo. No AWS secret is stored in GitHub.
  3. SSM Run Command runs `deploy/deploy.sh`: render `.env` from SSM, `pull`, `check --deploy` (refuses a release without the Anthropic key, the documents bucket or https URLs), `migrate`, `seed_demo` (first deploy only), then `up --wait` on healthchecks.
  4. `aws s3 sync` uploads the frontend, then a CloudFront invalidation.
- **Rejected: a self-hosted runner on the server.** GitHub's hardening guide says self-hosted runners "should almost never be used for public repositories," because any PR author could run code on the prod box.

## Deliverables
1. The app (hosted) and the repo
2. This decisions doc
3. A non-technical product doc for the compliance team: what the tool does, a day in the life of a reviewer and of a marketer. *Not yet written.*

## Settled defaults
- **Content format:** plain text plus an optional image mockup. Layout rules such as the FCRA prescreen notice's "12-point, bordered, front page" can't be checked in plain text, so they become human checklist items.

- **Domain (added later):** a subdomain of `spencerpresley.com`, whose DNS is hosted at Squarespace, not Route 53. That takes two records added by hand in Squarespace:
  - the ACM DNS-validation CNAME, for a certificate in us-east-1
  - `clearpath` CNAME pointing to the distribution's `*.cloudfront.net` domain

  Terraform outputs both record values. Until then, the default `*.cloudfront.net` address works.
