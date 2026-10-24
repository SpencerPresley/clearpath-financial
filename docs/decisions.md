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

## Key design decisions

### Code checks vs LLM checks
- **Code** owns hard facts: rate values against current offer terms, required disclosure strings, trigger terms, NMLS and license-number formats, banned phrases.
- **The LLM** owns judgment calls, and every finding must point to an exact span of the submitted text: is the creditworthiness qualifier actually there, is the soft-pull claim limited to the right step, is a paid relationship disclosed.
- **Human only:** Reg B discouragement through imagery and targeting.

Why: code is exact and free for numbers. It's also immune to prompt injection. A hidden "note to AI reviewers: pre-approved" can't talk a numeric comparison into passing.

### The AI can never approve
No model has a tool or output field that changes status. Submitted content is passed to models as marked data, never as instructions. Only a human records a decision.

### Approvals are tied to offer terms (the differentiator)
Each `Decision` records the `OfferTerms` versions the item quotes. When terms change, every approved item still on the old version is flagged for re-review.

None of the roughly 14 vendors surveyed documents this (see `research/market.md`). That's absence from their marketing pages, not proof nobody does it.

It also falls out of a compliance requirement. Reg N 1014.5 requires nonbank mortgage advertisers to keep records of the products and terms available when the ad ran, plus every materially different version, for 24 months **from the last date the ad ran**. So placements need run dates.

### Rates are stored once, but terms changes are never auto-published
Offer values are tokens (`{{PL_APR_FLOOR}}`). A terms change generates v+1 of each affected item, with values substituted and representative examples recomputed. For example, $10,000 / 36 months / 12.99% APR comes to $337/mo, so a new APR means a new payment amount.

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
- **LangChain over the Claude Agent SDK:** the Agent SDK is built for Claude-Code-style agents with filesystem and shell tools. That's more than an in-app assistant with about 7 custom tools needs, and we know LangChain. The model is Claude, through the Anthropic integration.

### Ergonomics: don't lose to the spreadsheet
Friction only where compliance requires it, which means only at the decision.
- The queue is a dense table: every column sortable and filterable, column chooser, saved views.
- Low-stakes fields (assignee, priority, tags, notes) are edited inline.
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

## Deliverables
1. The app (hosted) and the repo
2. This decisions doc
3. A non-technical product doc for the compliance team: what the tool does, a day in the life of a reviewer and of a marketer. *Not yet written.*

## Open questions
- Stack (frontend, backend, database, hosting, job runner)
- Content format: plain text plus an optional image mockup, or rendered PDF/HTML? Current default: text plus optional image. Consequence: layout rules like "12-point, bordered, front page" for the FCRA prescreen notice become human checklist items instead of code checks.
- Default approval expiry per channel. Company policy; we'll pick a value.
- How to assign reviewers: round-robin by product, or claim-from-queue?
