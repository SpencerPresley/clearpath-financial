# Foundation (workstream 0): review and resolutions

One fresh reviewer subagent (Opus) read the `ws0/foundation` diff against `main` (44e7264..ac71b4b) with the
spec, product-spec, decisions, the plan and the ledger's rulings, and ran its own probes in a scratchpad. Its
report is reproduced verbatim below, followed by what I did about each finding. Every code fix was test-first
(RED observed, then GREEN, then the full suite); commits are on `ws0/foundation`.

## Resolutions

Grading note: I fixed every Important finding except 10, which is a product call. I also fixed eight of the
thirteen Minors, because each was cheap now and would later force an edit in an app the finder doesn't own,
or because it broke a stated brief rule (no raw dicts).

| # | Finding | Resolution | Commit |
|---|---|---|---|
| I1 | Re-review loses priority in `in_review` | Fixed. Priority 0 iff `reopen_reason` set and status queued. I went one step past the suggested `(needs_rereview, in_review)`: a re-review can loop `changes_requested -> submitted` while the old version is still live (product-spec status machine), so `submitted` counts too. CHECK `item_rereview_has_reason` makes `needs_rereview` always carry a reason. E must clear `reopen_reason` when the re-review resolves or a new round starts from `expired` (documented on the field and in the report). Corrected in reviews 0001 (unmerged; Django can't alter a GeneratedField in place). | 3ceb981, 844566b |
| I2 | Decision/Placement can reference another item's version | Fixed with composite FKs `(version_id, item_id) -> reviews_version(id, item_id)` for Decision, Placement and `ReviewItem.current_version` (reviews 0005 unique + 0006 RunSQL). Kept the `item` FKs: queries filter on them constantly. | 3ceb981 |
| I3 | OfferTerms editable after citation | Fixed. Trigger `terms_offerterms_guard` (terms 0003) allows only closing an open-ended range (same lower bound, all other columns equal via `to_jsonb(NEW) - 'effective_range'`); DELETE refused. The product-match CHECK test moved to an INSERT. | 3ceb981 |
| I4 | Search outcome from another version | Fixed. Subquery scoped to `version=OuterRef("pk")`; fields renamed `version_outcome`/`version_decided_at` so the meaning is in the name. | 7d0e0fd |
| I5 | Trigram indexes unusable | Fixed. Indexes on `Upper(Cast("title", TextField()))` and `Upper("content_text")`; confirmed Django's Postgres `lookup_cast` emits `UPPER(%s::text)` for `icontains`. EXPLAIN test with `enable_seqscan=off`. | 3ceb981 |
| I6 | Default queue can't use the partial index | Fixed. `sort=queue` with no `status` implies `QUEUE_STATUSES`; explicit status wins; documented on the endpoint. | 7d0e0fd |
| I7 | Query-count tests missing | Fixed. One parametrized test over 22 read operations (every real list endpoint plus the detail reads that embed lists; 24 cases), growing every listed kind of row between two measurements. Verified it catches N+1 by dropping two prefetches (history 7 -> 19, comments 5 -> 9). | 9c89139 |
| I8 | `choices=` forces cross-app migrations | Fixed by dropping `choices=` everywhere and the `user_roles_known` CHECK (product-spec: a new role is "an addition, not a migration"). Convention test fails on any `choices=`. Adding the three user EventTypes later needed no migration, as intended. | c7ff088 |
| I9 | Two writers of `open_findings_count` | Fixed. `run_code_checks` returns `PersistedChecks(result, open_findings_count)`; `submit_item` writes that count. | 0aa6c68 |
| I10 | Attachment read permissions | **Not changed: your call.** Options and my recommendation are in the report's Open risks. | - |
| I11 | Legacy history for metrics | Fixed as recommended. `ItemImportedPayload.timeline: LegacyTimeline(submitted_at, first_reviewed_at, decided_at, outcome, rounds)`, all optional, dates validated in order. | 4044dae |
| M1 | No IntegrityError mapping for races | Deferred. A global 409 mapping would hide real bugs; the right fix is per service (`constraint_name` -> `InvalidInput`) in `create_saved_view` and partner create/rename. Low traffic, so a rare race gives a 500 that a retry fixes. | - |
| M2 | Tags silently truncated | Fixed. `Tag = Annotated[str, Field(min_length=1, max_length=50)]`; 422 otherwise. | 582a0f9 |
| M3 | Partner update gaps | Email pattern fixed. Clearing `agreement_signed_on` deferred: needs an explicit "clear" in the PATCH shape (None already means "leave as is"). | 2b3b4c6 |
| M4 | Three bare-dict returns | Fixed (`ItemHistory`, `SearchResults` via `search.search_library`, `MarkAllReadOut`); contract test rejects any dict-returning operation. | 582a0f9 |
| M5 | Dispatcher queues behind the lock | Fixed. `select_for_update(skip_locked=True)`; returns `busy=True`. Test proved it blocked 3 s before. | bb002a3 |
| M6 | Pool / resubmit notifications missing | Fixed. Pool assignment notifies active leads; sticky assignment says "back for your review". Resubmit notifications ride the sticky ITEM_ASSIGNED (decisions.md rule 1) rather than a second handler that would double-notify; E must record it. | 0ab54b6 |
| M7 | No user-management event types | Fixed. `user.created`, `user.roles_changed`, `user.active_changed` with payloads; stub docstrings name them. | d887a9f |
| M8 | No approved-date filter | Fixed. `approved_after`, `approved_before`, `approved_within_days`. | 5650e7b |
| M9 | Library hides lapsed approvals | **Not changed: your call** (report, Open risks). | - |
| M10 | TermsRef docstring says current version | Fixed: the approved version. | 113cae8 |
| M11 | No upload size limit | Deferred to A (deploy) or G: the limit belongs with the storage backend (S3 presigned uploads). | - |
| M12 | `listUsers` tagged admin | Fixed. New `users` tag/router. | 9c89139 |
| M13 | Attachment DELETE untested | Fixed (test added; the trigger already refused it). | 2b3b4c6 |

On the reviewer's rulings notes:
- **Ruling 1**: reversed, per I1.
- **Ruling 4**: I accept the understated cost. Two things are now recorded as open risks, not built: the
  cluster-wide xmin horizon, and the fact that every handler transaction holds an xid for its whole run.
  Mitigations for whoever owns ops (A): an "oldest undispatched event age" alert, and
  `idle_in_transaction_session_timeout`.
- **Ruling 14**: I11 was the counterexample, and it's now fixed.

After the fixes and a rebase onto `origin/main`:
- 622 backend tests pass (this branch's 296 plus C's 326 engine tests). The rebase also replaced this branch's
  `checks.contracts` with C's merged `checks.engine` types (no merged code imported it), and added an
  engine-compatibility test.
- ruff, pyrefly, makemigrations --check, manage.py check and the frontend checks are all clean.
- `make schema` has no drift.

The full transcript is in `docs/plan/reports/foundation.md`, under "Verification".

## The review (verbatim)

**Verdict: ready to merge with fixes.** The outbox, idempotent replay, immutability triggers, keyset pagination and the terms EXCLUDE constraint all hold up. Three things in `reviews` and `terms` should be fixed before E, F or G build on them, because the fix means a migration plus rows that become hard or impossible to correct later:

1. The queue priority stops ranking re-reviews first once a reviewer opens one.
2. A Decision or Placement can point at another item's version.
3. OfferTerms can be edited after an approval cites it.

I also confirmed two issues by running probes: precedent search labels a rejected version "approved", and the trigram indexes are never used. The suite passes: 234 tests, using suffix `review`. My probes live in the scratchpad (`/private/tmp/claude-501/-Users-spencer-code-promptarmor/51393cec-f963-4ef3-9f0b-5094c8f43a9e/scratchpad/probe/`), not the worktree, which I didn't modify.

#### Strengths
- **Focus 1 (late commits and concurrent dispatchers).** The cursor reads `(txid, id) > cursor AND txid < pg_snapshot_xmin(...)` (`audit/outbox.py:133-140`). Worked case: transaction A has xid 100 and is still open; B (xid 101) commits its event. The snapshot's xmin is 100, so B's event is held back, and both are delivered in order once A commits. An id-only cursor would advance past B and lose A. The test discriminates: it fails for an id-only cursor. Concurrent dispatchers serialize on `select_for_update`, and under READ COMMITTED the second one re-reads the advanced cursor.
- **Focus 2 (replay applies once).** `deliver` claims the receipt with `INSERT ... ON CONFLICT DO NOTHING RETURNING` before running the handler, in one transaction (`outbox.py:166-185`). A concurrent duplicate blocks on the unique index; if the first attempt fails, the receipt rolls back and a retry proceeds.
- **Focus 3 (immutable rows).** Triggers cover Event, Version, Decision, DecisionTermsVersion, DecisionEvidence and Attachment, and raw-SQL tests prove they fire. Using `restrict_violation` so Django raises `IntegrityError` is correct.
- **Focus 4 (keyset pagination).** One row-value comparison per sort, always ending in `id`, and the tie test is parametrized over every sort.
- **Focus 5 (terms overlap).** It raises `IntegrityError` with `constraint_name == "terms_no_overlap"`, and the same range on another product is accepted.
- The error envelope is mapped once. Endpoints contain no try/except. Event payloads are typed per EventType, with a completeness test. History entries are a discriminated union per type. Search snippets come back as structured parts, which is safe for untrusted copy. Real list endpoints are N+1-free as far as I can tell by reading them; only the queue is tested (see Important 7).

#### Issues

##### Critical (Must Fix)
None.

##### Important (Should Fix)

1. **A re-review loses its priority once a reviewer opens it.** `reviews/models.py:127-136`. Priority is 0 only for `status == needs_rereview`, but the product-spec status machine allows `needs_rereview → in_review`. After that move the item ranks as 10 + tier, behind fresh submissions.
   - Probe: an `in_review` item with `reopen_reason=terms_changed` and low tier sorted after a fresh `submitted` high-tier item (ORDER `[6, 5]`).
   - That breaks "re-reviews of live content first" for exactly the items someone is working on.
   - Fix now, while it's one reviews migration: base the expression on `reopen_reason IS NOT NULL AND status IN (needs_rereview, in_review)`, with E clearing `reopen_reason` when the item resolves.

2. **A Decision or Placement can reference another item's version.**
   - `Decision.item` and `.version` (`reviews/models.py:254-255`), `Placement.item` and `.approved_version` (`:353-354`), and `ReviewItem.current_version` (`:112`) are independent foreign keys.
   - Probe: `Decision(item=a, version=<version of item b>)` was accepted.
   - Decision is immutable, so a bad row can never be fixed. That undercuts "a decision references one exact version".
   - Fix: add `UniqueConstraint(fields=["id", "item"])` on Version, plus a composite FK via RunSQL, e.g. `(version_id, item_id) REFERENCES reviews_version(id, item_id)`. The alternative is to drop the redundant `item` FK.

3. **OfferTerms can be edited after an approval cites it.** `terms/models.py:16`; it isn't in `reviews/migrations/0002_immutable_records.py`. An `UPDATE ... SET values=...` silently rewrites "the offer-terms versions it quotes" on every past Decision. Fix: a trigger that rejects any UPDATE except changing the upper bound of `effective_range` (closing the range is the only legitimate edit), and rejects DELETE.

4. **Precedent search shows the item's latest outcome next to a different version's text.** `reviews/search.py:59-69`. The hit is the latest *matching* version, but `latest_outcome` comes from the item's latest Decision on any version.
   - Probe: v1 contains "won't affect your credit score" and was rejected; v2 dropped the phrase and was approved. The hit returned `(version_n=1, APPROVED)`.
   - A reviewer would take a rejected phrasing as precedent for approval.
   - Fix: filter the decision subquery with `version=OuterRef("pk")`, and return no outcome when that version has no decision.

5. **The trigram indexes are never used.** `item_title_trgm_idx` and `version_content_trgm_idx` (`reviews/models.py:174, 220`) index the bare column, while `icontains` compiles to `UPPER(title::text) LIKE UPPER(...)`.
   - EXPLAIN with `enable_seqscan=off` still chose `Seq Scan ... Filter: (upper((title)::text) ~~ '%LOAN%')`, and the same for `content_text`.
   - So the brief's "trigram on title" requirement is met on paper only, and `find_phrase` scans every version.
   - Fix: index the expression the queries actually use, e.g. `GinIndex(OpClass(Upper(Cast("title", TextField())), name="gin_trgm_ops"))` and `Upper("content_text")`.

6. **The default queue can't use the partial queue index.** `list_items` with an empty `ItemFilter()` (`reviews/selectors.py:252`) sorts every status by `queue_priority`. EXPLAIN showed a full sort with no partial index. With an explicit status filter, the planner used the queue partial index.
   - Approved, rejected and legacy items also interleave into the "queue" sort.
   - Fix: have `ItemSort.QUEUE` imply `QUEUE_STATUSES` when no `status` is given, or state in the contract that the frontend must always send the statuses. This needs settling before H (the queue frontend) builds on it.

7. **Spec §6.3 requires a query-count assertion on each list endpoint; only `listItems` has one** (`reviews/tests/test_selectors.py:59`). Fifteen-plus real list endpoints have none, including listDecisions, listComments, listVersions, listPlacements, listItemAttachments, listPartners, listFindings, getItemHistory, searchLibrary and listNotifications. They look clean today, but E and G will add fields to `DecisionRow` and the evidence rows with nothing to catch N+1. Fix: one parametrized 3-rows-vs-30-rows test per endpoint.

8. **Every enum-backed field carries `choices=`, so adding an enum member forces migrations in apps the adder doesn't own.**
   - `enum_choices` (`core/db.py:15`) is used in every model; there are 15 `choices=` entries in the reviews 0001 migration alone.
   - Example: E adds an expiry-warning `NotificationKind`. `migrations-check` then fails until someone migrates `notifications`, an app E doesn't own.
   - Those choices also give no DB enforcement: `status` has no CHECK constraint, unlike `roles`.
   - Ruling 13 fixed the rename case but not the add case.
   - Fix: drop `choices=` (enums are already enforced at the schema edge), or deliberately pair each with a CHECK constraint and accept that adding a member costs a migration. Pick one now.

9. **Two writers of `open_findings_count`.** `reviews/services.py:133` sets it to `len(checks.findings)`. The seam docstring at `checks/services.py:8-15` says C's `run_code_checks` will set the count itself, carrying dismissals forward. Whichever is implemented, `submit_item` overwrites it, and it counts carried-dismissed findings as open. Since this is the reference action others copy, the bug spreads. Fix: the seam returns the persisted open count, and `submit_item` uses that.

10. **Who can read and download attachments needs a decision from you.**
    - `GET /attachments/{id}/download` (`reviews/api.py:235`, `records.py:424`) has no role or owner check.
    - Uploading partner attachments is Lead-only, and product-spec lists the Partners screen as Lead, yet any authenticated marketer can download partner agreements and decision evidence.
    - `getPartner` exposes the `download_url`s with no role check either.
    - The spec doesn't settle who may read these. Who may read partner agreements and decision evidence is your call, not something I can verify.

11. **Legacy history has nowhere to go for metrics. This needs a ruling now.**
    - `Decision.version` is NOT NULL and legacy items have no versions, so G can't create Decisions for imported rows.
    - `ItemImportedPayload` (`audit/payloads.py:105-108`) carries only `import_id`, `legacy_ref`, `row_number`.
    - The only legacy dates on the model are `submitted_at` and `approved_at`. That leaves no first-review date, decided-at for rejected rows, or round count, which the spec's metrics (time to first review, rounds per item) need from "events plus imported history".
    - Payloads are add-only by convention, so this is cheap now and locked later.
    - Recommendation: put the legacy timeline in `ItemImportedPayload` (submitted, first reviewed, decided, outcome, rounds). That needs no reviews migration.

##### Minor (Nice to Have)
- **No `IntegrityError` mapping anywhere** (`config/api.py:57-60`). Check-then-insert races in `create_saved_view` (`reviews/services.py:387`) and in partner create/rename (`partners/services.py:47, 79`) return a bare 500. `core.db.constraint_name` exists for exactly this and is never used outside tests.
- **Tags are silently truncated.** `SubmitItemIn.tags` and `ItemUpdateIn.tags` have no per-element limit (`reviews/schemas.py:109, 125`). Probe: a 60-character tag returned 201 and was stored as 50 characters. Fix: `list[Annotated[str, Field(min_length=1, max_length=50)]]`.
- **Partner update gaps.** `PartnerUpdateIn.contact_email` (`partners/schemas.py:54`) lacks the email pattern `PartnerIn` has. Because None means "leave as is" (`partners/services.py:85`), `agreement_signed_on` can never be cleared.
- **Three endpoints return bare dicts**, against the brief's "no raw dicts across boundaries": `reviews/api.py:159`, `reviews/api.py:390`, `notifications/api.py:30`.
- **The dispatcher queues instead of skipping.** `select_for_update()` (`outbox.py:150`) holds the cursor lock across up to 500 × N Redis `.delay()` calls. With beat every 2 s, a slow Redis stacks dispatchers behind the lock. Fix: `skip_locked=True` and return early.
- **Missing notifications for decisions.md rules.** "Nobody eligible: lead notified" isn't handled: `notify_assignee` returns when the assignee is None (`notifications/handlers.py:40`). "Resubmit: the assignee is notified" has no handler on `ITEM_RESUBMITTED`. E would have to edit `notifications`, which it doesn't own.
- **No event types for user management** (`core/domain.py:229`): no user created, role changed, or deactivated. The admin `updateUser` stub will change roles with nothing to record. Role grants are exactly the audit-trail gap the anti-goals forbid.
- **The ItemFilter has no approved-date range** (`reviews/filters.py`), but the board's "Approved (last 14 days)" column needs one.
- **The library hides past approvals.** It forces `status=[approved]` (`reviews/api.py:379`), so expired, needs-re-review and withdrawn items that were once approved drop out of the "approved archive". This is a judgment call: an archive of past approvals should include lapsed ones.
- **`TermsRef` defines "quotes v12" against the current version** (`checks/models.py:85`). After F generates a fast-track v+1, current is no longer the approved version; it should say "the approved version".
- **No upload size limit** on attachments.
- **`listUsers` is tagged `admin`** but serves every user's pickers, so the generated hook lands in the admin module.
- **Attachment DELETE is untested;** only UPDATE is. The trigger covers both.

#### Rulings I disagree with
- **Ruling 1 (queue priority from `status=needs_rereview`): disagree.** Its stated cost ("an item whose placement lapsed sorts too high") points the wrong way. The real cost is Important 1: a live-content re-review sorts too low as soon as it moves to `in_review`, which the status machine allows.
- **Ruling 4 (`(txid, id)` cursor with snapshot xmin): agree, but the cost is understated.**
  - The xmin horizon is cluster-wide, so a transaction in *any* database on the server holds dispatch back. On the shared compose Postgres that includes other worktrees' test runs; the test's own comment at `test_outbox.py:197` concedes this.
  - `deliver` inserts the receipt first, so every handler transaction holds an xid for its entire run. Any slow handler, such as an inline LLM call or F's fan-out, stalls the whole outbox.
  - Mitigations: log when the oldest undispatched event's age exceeds N seconds, and set `idle_in_transaction_session_timeout`.
- **Ruling 14 (extra columns so others needn't migrate reviews): mostly agree.** Important 11 (legacy history) is a counterexample.
- **Ruling 13 (`.value` in migrations): agree.** It covers renames but not new members (Important 8).
- **Agree as stated:** 3 (lead implies reviewer), 5 (`effective_roles` on MeOut), 10 (`restrict_violation`), 20 (structured snippets, a real security win), 21 (RawSQL keyset), 23 (`{int:}` path converters), 24 (`list(...)` returns), 27 (own-transaction read; the dispatcher writes no events).
- **Ruling 25 (extra real endpoints): fine,** but they bring WS0-owned permission and query-count obligations (Important 7 and 10).

#### Declined to judge
- Behavior behind the 501 stubs: owned by C, D, E, F, G, K and L.
- Generated TS client and frontend: out of scope per the brief.
- Conformance to `samples/README.md` import messes: the file doesn't exist yet (B hasn't merged).
- The 50k-item `EXPLAIN ANALYZE` p95 test: it needs L's seed and isn't in the WS0 plan. I only checked index *usability*.
- S3 storage, MFA flows, and allauth beyond the login round trip: owned by A or outside the plan.
- The sweep's day boundary and `TIME_ZONE`: E's sweep.
- Whether marketers may read all items and comments: the spec intends queue visibility ("No status chasing").
- `age_days` using `submitted_at` for re-reviews: depends on whether E resets `submitted_at` on reopen.
- The LangGraph checkpointer holding transactions open, and its effect on the xmin horizon: K's implementation, which I can't verify yet.
- Historical seeded events flooding notifications through dispatch: L's seeding strategy.

#### Assessment
**Ready to merge? With fixes.** Nothing is architecturally wrong, and the five focus invariants hold. Before E, F and G land rows, fix the three migration-shaped items (queue priority expression, version-consistency FKs, OfferTerms immutability), plus the search outcome bug and the trigram indexes. Settle the attachment read policy (Important 10) and the legacy-history ruling (Important 11) with you first.
