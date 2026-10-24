# Offer terms (workstream F): report

Branch `wsF/offer-terms`, closes #7. Plan: `docs/plan/offer-terms.md`. Review with resolutions:
`docs/plan/reviews/offer-terms.md`.

Executed natively, then one fresh whole-branch reviewer. The five tasks share one selector
(`terms.selectors.affected_approvals`) and one per-item service (`terms.fanout.fan_out_item`), and all of them sit
on E's lock-order and gate contracts.

## What shipped

| Area | Where | Notes |
|---|---|---|
| Publish | `terms/services.py` | Lead only; per-product advisory lock; closes the open range at `now` and inserts v+1 from `now`; TERMS_PUBLISHED with `affected_item_ids` |
| Work list | `terms/selectors.py::affected_approvals` | Approved non-legacy items whose approved version quotes superseded terms, plus needs_rereview items whose current copy does; 4 queries |
| Fan-out | `terms/fanout.py`, `terms/handlers.py`, `terms/tasks.py` | Handler `terms.fan_out` enqueues one task per item on commit; each task is one transaction; 15-minute reconcile beat |
| Fast-track | `terms/fast_track.py` | Single and bulk over E's `record_decision(lane=FAST_TRACK)` and `run_bulk` |
| Impact preview | `terms/impact.py` | Read-only dry run of the render against the proposed values |
| API | `terms/api.py` | `fast_track_router` (tag `decisions`) replaces E's bulk stub in `reviews/api.py` |

## The worked example, end to end

`terms/tests/test_handlers.py::test_full_path_through_the_outbox` runs the whole path:
- The approved, live copy reads "…a $10,000 loan over 36 months at 7.49% APR has 36 monthly payments of $311.
  Rates from 7.49% APR to 35.99% APR…".
- The lead publishes `apr_min = 12.99`. `dispatch_pending` → `deliver("terms.fan_out")` → the per-item task runs.
- v2 reads "…at 12.99% APR has 36 monthly payments of $337. Rates from 12.99% APR…". It has origin `fast_track`,
  is based on v1, has `llm_check_status=skipped` and zero open findings (v1's dismissals carried).
- The item is now `needs_rereview(terms_changed)` and assigned back to the approver.
- The approver's one-click fast-track records a `fast_track`-lane decision that quotes the new terms, with
  `ai_review_carried_from_n = 1`.
- Redelivering the event returns `duplicate`. The non-live sibling goes to `expired(terms_changed)`.

## Interfaces for the frontend (J)

### `POST /api/terms` (`publishOfferTerms`, tag terms). Lead only.

Body: `OfferTermsPublishIn {product, values, based_on_terms_id, note?}`.
- **`effective_from` was removed**: a version takes effect now (ruling 1 below).
- **`based_on_terms_id` is required**: the id of the version in effect when the form and preview loaded
  (`GET /terms/current`), or `null` for a product's first terms. If another lead published since, the save is a
  409 `conflict` ("The offer terms changed since you opened this (v3 is in effect now). Review the impact
  again."). On that 409, reload the terms and re-run the preview. Without this check, B's save would silently
  put back the rate A just changed.
- 201: `OfferTermsOut` (the new version, `is_current: true`).
- 403 `not_permitted` for anyone but a lead.
- 422 `invalid_input` with `fields[0].loc = ["body","values"]`, in two cases: the values match the version in
  effect ("Nothing changed: these are v3's values."), or the values are for another product.
- 409 `conflict` for a stale `based_on_terms_id` (above). 409 `terms_range_overlap` should not occur: `now` is
  read after the per-product lock.

The fan-out runs in the background, typically within seconds (outbox beat every 2 s). Invalidate the queue,
item, and terms queries after a publish.

### `POST /api/terms/impact-preview` (`previewTermsImpact`). Lead only. Writes nothing.

Body: `{product, values}`, the same shape as publish. Response `ImpactPreviewOut`:

| Field | Meaning |
|---|---|
| `summary` | Ready-to-show copy (below) |
| `current_terms_id`, `current_version` | The version in effect; null for a product's first terms |
| `next_version` | What the save will create |
| `approved_items_quoting` | Approved items whose approved version quotes the terms (all versions count as superseded by the save) |
| `will_need_rereview` / `will_expire` | Of those: live / not live (ruling 2) |
| `already_in_rereview` | needs_rereview items whose copy quotes the terms; they get a generated version, status unchanged |
| `normal_lane` | Affected items that can't be fast-tracked (`StaleTermsRef`) |
| `changed_fields` | `TermsField[]` that differ from the version in effect (`issuing_bank` and `purchase_apr_variable` aren't TermsFields, so they don't appear) |
| `items[]` | `{item: ItemRowOut, is_live, quoted_fields, will_become, lane: "fast_track"\|"normal", numbers_change}` |
| `partners[]` | `{partner: PartyRefOut, item_count}`, most items first |

`numbers_change: false` means none of the numbers the item quotes change. Its generated version has no diff,
but it still goes through re-review (ruling 3).

Summary copy (`terms/impact.py::_summary`):
- "14 approved items quote v12; 9 will need re-review, 5 will expire."
- Singular: "1 approved item quotes v12; 1 will need re-review."
- With re-reviews: "… 2 items already in re-review will get the new numbers."
- Nothing affected: "No approved items quote v12." For a first version: "No approved items quote the current terms."
- Unchanged values: "These are v12's values; nothing would change." Disable Save in this case; publish would 422.

### `POST /api/items/{id}/fast-track-approve` (`fastTrackApprove`, tag decisions). New. The assignee or a lead.

Body: `FastTrackIn {version_n, reason}`. Send the generated version's `n`, the one the reviewer saw. Returns 201
`DecisionOut` with `lane: "fast_track"` and `ai_review_carried_from_n` set.

409 codes:
- `stale_version`: a newer version exists.
- `invalid_transition`: the item isn't in needs_rereview.
- `conflict`: the current version isn't generated.
- `open_findings_block_decision`, `accepted_findings_block_approval`, `stale_offer_terms`.

### `POST /api/items/bulk/fast-track-approve` (`bulkFastTrackApprove`). Lead only.

> Updated by the fast-track polish follow-up (PR #33), superseding ruling 6 below.

Body: `{item_ids (1–500), reason, seen_versions: [{item_id, version_n}] (1–500)}`. Returns 200
`BulkResultOut {succeeded[], skipped[{item_id, code, message}]}`.

- **Lead only:** anyone else gets 403 `not_permitted` (product-spec Roles: bulk actions are Lead). A reviewer
  fast-tracks one item at a time with `fastTrackApprove`, at the version on screen.
- **`seen_versions` is required, with one entry per item**: the `current_version_n` each row showed. If any item in
  `item_ids` has no entry, the request is a 422 `invalid_input` on `["body", "seen_versions"]` naming the items
  ("Send the version you saw for every item; missing for CP-12."), and nothing is approved. Each item is approved
  only at its listed version, else skipped as `stale_version`. A version that a later terms change generated after
  the page loaded is never approved unseen.
- Callers: the queue's bulk bar (`features/queue/BulkBar.tsx`) sends `seen_versions` from each selected row. The
  review screen uses the single endpoint.
- Skip codes: `open_findings_block_decision` (send these to the normal lane), `invalid_transition`,
  `stale_version`, `not_found`, `stale_offer_terms`, `accepted_findings_block_approval`.

### Diff

Use the existing `GET /api/items/{id}/diff?from_n=<latest_decision.version_n>&to_n=<current_version_n>`. Only the
numbers differ: `test_diff_of_generated_vs_approved_touches_only_the_numbers`.

### Fast-track lane in the queue

There's no new filter. The rule is `status=needs_rereview` and `current_version.origin == "fast_track"`, which is
already I's `fastTrackAvailable`. `reopen_reason=terms_changed` finds the terms re-reviews. Items with
`approval_expired` can now also have a generated version (ruling 7). I's `rereviewActions` already offers
Fast-track for them, but it also offers Reaffirm, which E's gate refuses once the copy quotes superseded terms.
J or I should drop Reaffirm whenever `fastTrackAvailable` holds.

## Backend interfaces

```python
terms.services.publish_terms(*, actor, data: PublishTermsInput(product, values, based_on_terms_id, note=""), clock) -> int
terms.selectors.terms_in_effect(*, product, clock) -> OfferTerms | None
terms.selectors.affected_approvals(*, product, clock, item_ids=None, if_published_now=False, statuses=AFFECTED_STATUSES)
  -> tuple[AffectedApproval]
  AffectedApproval(item_id, status, version_id, version_n, content_text, refs: tuple[TermsRefDraft], quoted_terms_ids)
terms.fanout.fan_out_item(*, item_id, clock) -> FanOutOutcome
  # reopened_fast_track | reopened_normal_lane | expired | expired_normal_lane | regenerated | regenerate_failed | skipped
terms.fast_track.fast_track_approve(*, actor, item_id, version_n, reason, clock) -> DecisionResult
terms.fast_track.bulk_fast_track_approve(*, actor, item_ids, reason, seen_versions, clock) -> BulkResult  # lead only
terms.impact.impact_preview(*, viewer, product, values, clock) -> ImpactPreview
Celery: terms.fan_out_item(item_id) (autoretry), terms.reconcile_fan_out (beat, 900 s)
Outbox handler: terms.fan_out (TERMS_PUBLISHED)
```

## Rulings made here (reversible)

1. Ruling: a publish takes effect now; `effective_from` is gone from the API. `run_code_checks` links v+1's
   TermsRefs to the terms in effect when the check runs, so a future-dated version fanned out at publish would
   generate copy quoting the old version, and E's `stale_offer_terms` gate would then refuse it. Cost if wrong:
   scheduled terms need the field back plus a beat job at the effective instant.
2. Ruling: identical values are refused (422). Publishing them would send every quoting item to re-review for
   nothing. Cost if wrong: one check.
3. Ruling: an item is affected if it quotes the superseded version, even when none of its quoted numbers change.
   This is the spec read literally. Its generated version has no diff and clears in one click, and the preview
   flags it with `numbers_change: false`. The alternative, skipping it, would leave its approval quoting a dead
   version. E's gates then refuse a later reaffirm, and the next publish would catch it anyway. Cost if wrong: a
   filter in `affected_approvals`, plus a decision about what the skipped items' approvals quote.
4. Ruling: the task renders with the terms in effect when it runs, not the event's terms. If v14 lands before
   v13's tasks drain, items go straight to v14. Idempotency comes from the same check: once sent back, an item
   isn't approved, and once fast-tracked it quotes current terms. Cost if wrong: none found.
5. Ruling: the generated version's author and the reopen/expire events' actor are the lead who published the
   terms in effect (`Version.author` is non-null). Cost if wrong: a system user.
6. **Superseded (PR #33): bulk is Lead-only and `seen_versions` is required.** Ruling: bulk fast-track is open to reviewers, scoped per item to their own. The merged review screen calls
   bulk as the assignee. product-spec Roles lists bulk actions under Lead, but each item gets the same check as a
   single fast-track. Cost if wrong: `require_role(LEAD)` in one place, plus I switching to `fastTrackApprove`.
7. Ruling: items already in needs_rereview whose copy quotes superseded terms get a fresh generated version and
   keep their status. This covers re-review for expiry, and a second terms change landing before the first was
   fast-tracked. The live content runs the old numbers, and without the new version the item can be neither
   reaffirmed nor fast-tracked; it can only be claimed into a full review. The new version is always rendered
   from the approved text, never from an earlier generated one. Cost if wrong: drop needs_rereview from
   `AFFECTED_STATUSES`.
8. Ruling: the handler enqueues on commit (`robust=True`, so one broker error doesn't drop the rest), and a
   15-minute reconcile beat backs it up. The reconcile covers approved items only: a needs_rereview item whose refs
   don't fit its copy would otherwise be re-run every pass. The handler runs inside
   its receipt's transaction, and a direct `.delay` under eager mode would nest every item in one transaction.
   The reconcile closes the window where a worker dies between the receipt's commit and the enqueue: nothing else
   leaves an approval quoting superseded terms. Cost if wrong: one beat entry.

## Shared-file touches (outside `terms/**`)

- `backend/reviews/api.py`: removed the `bulkFastTrackApprove` stub and its schema import. The operation id, path
  and tag are unchanged; it now lives in `terms/api.py`.
- `backend/reviews/schemas.py`: `BulkFastTrackIn` moved to `terms/schemas.py`, gaining optional `seen_versions`.
  The generated model name and the existing `{item_ids, reason}` calls are unchanged.
- `backend/config/api.py`: registers `terms.api.fast_track_router`.
- `backend/config/settings/base.py`: beat entry `terms-fan-out-reconcile`.
- `backend/config/tests/test_contract.py`: removed the three implemented stubs and the now-dead terms body
  branch; `test_stub_still_validates_input_first` retargeted to `/items/fetch-url`.
- `frontend/openapi/ninja.json`, `frontend/src/api/generated/**`: regenerated.
- No edits to `reviews/` services, `checks/` (D2's area), or `audit/`.

## Verification

At the branch head, rebased on `origin/main` (`7680525`, includes the LLM wiring #30), test DB suffix `wsF`.

```
$ uv run pytest -q
1283 passed, 2 deselected
$ uv run --group lint ruff check . && uv run --group lint ruff format --check .
All checks passed!
$ uv run --group typecheck pyrefly check
 INFO 0 errors
$ manage.py makemigrations --check --dry-run
No changes detected
$ make schema (export + generate:api) → committed; npm run typecheck / test:run (393 passed) / lint / format:check: ok
```

Tests (58 in `terms/tests`):
- Worked example: through the services and through the outbox.
- Live vs not live; the StaleTermsRef lane.
- Idempotency under redelivery and re-run; an item the sweep moved first; renders against later terms;
  re-review regeneration and a second terms change.
- Bulk partial success: clean, open finding, wrong state, missing item.
- Bulk scoped to the reviewer's items; permissions on every endpoint.
- Diff touches only the numbers.
- Preview: counts, lanes, partners, writes nothing, a flat query count.
- Concurrency: a fan-out next to a claim finishes. A fan-out next to the expiry sweep finishes with per-item
  transactions, and the single-transaction control raises `deadlock detected`, which proves why the per-item
  rule exists.

## Open risks / follow-ups

- **A claimed re-review loses the fast-track lane on a later terms change.** Once claimed, the item is in_review,
  which isn't in `AFFECTED_STATUSES`, so a second publish doesn't regenerate it. It isn't stuck: approve-with-edits
  and request-changes work. Review M3.
- **The publish event's `affected_item_ids` is unbounded.** That's fine at demo scale. Cap it, or store a count,
  if volume grows (review M5).
- **In-flight reviews quoting the old terms** (submitted or in_review when terms change) aren't touched. E's
  `stale_offer_terms` gate then refuses Approve, so the reviewer has to Approve with edits (v+1 is checked against
  the new terms) or Request changes. This is out of F's scope as briefed. A cheap option: the fan-out adds a
  generated version to these items too.
- **Expired items regenerate only at publish.** An expired(terms_changed) item whose generated version is itself
  superseded by a later publish starts its new round from stale numbers. Code checks then flag them
  (`pricing.terms_current`). Low stakes: nothing is live.
- **`changed_fields`** doesn't list `issuing_bank` or `purchase_apr_variable` changes, because they aren't
  `TermsField`s.
- **Time-sensitive API tests.** Tests that use the API with E's fixed test clock (2026-10-24 15:00 UTC) depend on
  real time being later than that, which holds from now on.
