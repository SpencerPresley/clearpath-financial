# Product spec

The workflow, data model, screens, and automation. For the reasons behind each choice, see `decisions.md`.

## What it does that a spreadsheet can't

The spreadsheet *records* state, and someone has to type every change into it. The tool *owns* the item: state changes only through actions, each action requires certain fields, and the side effects happen automatically.

1. **The content lives in the item, with versions.** "Which file is v3" can't come up.
2. **A version can't be approved with open findings.** Every finding must be accepted or dismissed, and a dismissal needs a reason.
3. **An approval records what it was approved against:** the version, offer-terms versions, rule-set date, evidence, approver, and expiry.
4. **Every action writes an event.** The audit trail, notifications, metrics, and re-review triggers all come from that one log.

## Roles
- **Marketer:** submits items and responds to requested changes.
- **Reviewer:** reviews items and records decisions.
- **Compliance Lead:** everything a reviewer can do, plus editing offer terms, managing partners, and bulk actions.
- **Admin:** user management and import.

A user's roles are stored as a list, so a future `partner` role is an addition, not a migration.

## Entities

```
User(name, email, roles[])
Partner(name, type: affiliate | lead_gen | marketplace, status)
OfferTerms(product, version, apr_floor, apr_ceiling, fees{}, effective_from, effective_to)
Rule(id, citation, kind: code | llm | human, jurisdiction, products[], channels[], effective_from)
ReviewItem(title, product, channel, partner_id?, markets[], owner, assignee, status, round,
           tags[], notes, reopen_reason?)
Version(item_id, n, content_text, author, created_at, terms_refs[])
Attachment(owner: item | version | partner | decision,
           kind: creative | substantiation | agreement | rate_sheet | criteria | screenshot | other,
           file, sha256, uploaded_by, at)                      -- immutable; "replace" adds a row
Finding(version_id, rule_id, source: code | llm, span, quote, message, suggested_fix,
        state: open | accepted | dismissed, reason, resolved_by)
Comment(version_id, span?, author, body)
Decision(version_id, outcome: approved | approved_with_changes | changes_requested | rejected,
         approver, reason, terms_versions[], ruleset_date, evidence[{attachment_id, sha256}],
         expires_at)
Placement(item_id, approved_version_id, location/url, first_run, last_run, monitored,
          takedown_state?)
Snapshot(placement_id, fetched_at, text, result)               -- stretch goal
Event(entity, entity_id, type, actor, at, payload)             -- append-only
```

Products: personal loan (PL), credit card (CC, issued through a sponsor bank), mortgage prequalification (MTG).

## Status machine

```
draft → submitted → in_review → changes_requested → (new version) → submitted …
                              ↘ approved | rejected
approved → needs_rereview     (automatic: terms changed, approval expiring, drift found; only if live)
approved → expired            (approval expired with no active placement)
needs_rereview → fast-track approve | pull (takedown) | reaffirm (same version) | in_review
```

- **Approve-with-changes:** the reviewer's edits create v+1, authored by the reviewer, and that version is the one approved.
- **Round** goes up each time the item is resubmitted after `changes_requested`.

## Screens

| Screen | Who | What it does |
|---|---|---|
| **Queue** | Reviewer, Lead | A dense table: every column sortable and filterable, column chooser, saved views (my queue, unassigned, waiting >3 days, needs re-review). Shows each item's age and open-finding count. Low-stakes fields (assignee, priority, tags, notes) are edited inline. Bulk actions. A stats strip at the top. Clicking a row opens a **preview drawer**. **Board toggle** (see below). |
| **New submission** | Marketer | Product, channel, partner, markets, planned run dates, copy (pasted, or fetched from a URL), optional mockup, evidence uploads. **Code checks run live as the marketer types.** |
| **My submissions** | Marketer | What's waiting on me, and why. Replaces "any update?" emails. |
| **Review** | Reviewer | See the layout below. |
| **Offer terms** | Lead | Edit terms, which creates a new version. An **impact preview** ("14 approved items quote v12; 9 will need re-review") appears before confirming. |
| **Library / search** | Everyone | The approved archive, plus precedent search (e.g. "won't affect your credit score" turns up past decisions). **Export**: filter by product, channel, partner, or run-date range to get an xlsx index plus, per item, the approved version, decision record, terms snapshot, and evidence hashes. |
| **Partners** | Lead | Each partner's agreement and evidence, items, findings history, and repeat issues. |
| **Import** | Admin | Upload an xlsx, or "Load sample tracker". Map columns, map status values, preview problems, commit. Imported rows become legacy items that carry their history. |
| **Outbox** | Everyone | Emails the assistant sent after a human approved them (demo stand-in for real mail). |
| **Assistant** | Everyone | A side panel. See `decisions.md` → Assistant. |

### Review screen layout

```
┌─ [Status ▾] Approve · Request changes · Reject ─────────── sticky ┐
│                                     │ Findings (3) | Comments |    │
│  Copy / mockup, flagged spans       │ Details | Evidence | History │
│  highlighted                        │                              │
│  [v2 ▾] compare with [v1 ▾]         │ ● Rate claim: "as low as"    │
│                                     │   needs range + qualifier    │
│                                     │   [Accept] [Dismiss…]        │
└─────────────────────────────────────┴──────────────────────────────┘
```

The content takes the center because reviewing it *is* the work. The Details tab and the History timeline (the event log, rendered) are borrowed from Jira.

### Board view

Columns: Submitted · In review · Changes requested · Needs re-review · Approved (last 14 days). Each card shows the item's age, open-finding count, partner, and assignee.

The only drag allowed is Submitted → In review ("claim"). Every other move opens the item.

## Automation

| Trigger | Effect |
|---|---|
| Submit, or new version | Code checks run synchronously. LLM checks run as a background job (a few seconds). Quoted rates are linked to `OfferTerms` versions. Resubmitting bumps the round. The assignee is notified. |
| Finding accepted | It becomes a required change in the request-changes message. |
| Decision | Blocked while any finding is open. Records terms versions, rule-set date, evidence, and expiry. Notifies the submitter. |
| New `OfferTerms` version | Generates v+1 for affected live items (tokens substituted, representative examples recomputed). Sets them to `needs_rereview(terms_changed)` in the fast-track lane. |
| Daily sweep | Expiry warnings at 30 days. Expired items move to `needs_rereview` (if live) or `expired`. Retention dates updated. Drift fetch (stretch). |
| Every action | Writes an `Event`, which feeds the audit trail, notifications, and metrics. |

## Checks

**Code:**
- rate values against current `OfferTerms`
- Reg Z trigger terms and the disclosures they require
- required disclosure strings
- CA §22162 license disclosure (configurable phrase list)
- card issuer line
- banned phrases: government/FHA, debt-wipe language, "guaranteed" / "pre-approved" without a prescreen record

**LLM, each finding pointing to an exact span:**
- "as low as" without a creditworthiness qualifier
- a soft-pull claim not limited to the right step
- a paid relationship not disclosed

**Human only:**
- Reg B discouragement through imagery and targeting
- layout rules that plain text can't show

The full rule list with citations is in `research/regulations.md` → "Rule checks for the pre-reviewer".

## Metrics

All metrics are computed from the `Event` log, and the imported history is real data:
- time to first review
- time per round
- number of rounds per item
- time to fix live content (`needs_rereview` → resolved)
- items waiting more than N days

## Drift monitoring (stretch)

1. Fetch the page: `httpx` plus `selectolax`/BeautifulSoup for static pages, Playwright for JavaScript-rendered pages.
2. Extract the visible text.
3. Fuzzy-locate the approved copy (rapidfuzz). The result is unchanged, modified (with a diff), or missing.
4. Re-run the code checks against the whole page.

We don't diff the whole page, because ads, dates, and navigation change constantly. The demo uses 2–3 affiliate pages we host ourselves, with a "simulate edit" button.
