# Review: import, export, and evidence packs (workstream G)

One fresh reviewer (general-purpose subagent, no prior context) read the branch against docs/spec.md, samples/README.md,
the foundation report, the ledger, and the plan. It also ran the suite plus probe scripts. Its baseline: 862 tests
passed, ruff and pyrefly clean, the exported schema identical to the committed one. Its findings are below, each
with what was done about it. The reviewer's probes are in the session scratchpad; it edited nothing in the repo.

## Important

| # | Finding (reviewer's evidence) | Resolution |
|---|---|---|
| 1 | **A corrupt xlsx returns 500, not 422.** A valid zip with broken XML in `xl/workbook.xml`, a sheet, or `[Content_Types].xml` raises `xml.etree.ElementTree.ParseError`, which isn't in `read_workbook`'s except tuple (reproduced). | Fixed: `ParseError` caught at the parse boundary. `test_a_zip_with_broken_xml_is_not_a_workbook` covers all three parts. |
| 2 | **One stray cell makes a tiny upload take 11+ s in the request.** `ws.iter_rows()` is unbounded, and openpyxl builds every cell in `max_row × max_col`. A 5 KB file with a blank at (20000, 200) took 11.4 s (reproduced). | Fixed: header detection reads at most 10 rows × 100 columns. Body reads are as wide as the header. A tracker whose used range runs more than 10,000 rows below the header is refused, with a message saying to delete the stray cells. The upload cap is 5 MB (was 10). Tests: `test_a_stray_cell_far_right_and_below_is_not_read` (< 3 s; unbounded it's 2.7M cells), `test_a_used_range_far_below_the_data_is_refused`. Not added: defusedxml. Expat already limits entity amplification; noted in the report. |
| 3 | **A partner whose app spelling differs by spaces or punctuation gets a duplicate.** Rows resolve by `partner_key`, but `_ensure_partners` matched on `casefold()`. With "Lend Compare" in the app, the sample created an unused "LendCompare" (reproduced). | Fixed: `_ensure_partners` and the partner-id lookup both key on `partner_key`. `test_existing_partners_are_reused_not_duplicated` is parametrized over `lendcompare`, `Lend Compare`, and `Lend-Compare`, and asserts 7 partners created and both sheet rows linked to the existing one. |
| 4 | **Exported xlsx can contain live formulas, and a control character breaks every export of the view.** openpyxl writes `=…` strings as `<f>`, so a title `=HYPERLINK(...)` becomes a working formula. A `\x0b` raises `IllegalCharacterError` (both reproduced). | Fixed: every string cell is written with `data_type="s"`, and `ILLEGAL_CHARACTERS_RE` is stripped first. Tests: `test_user_text_that_looks_like_a_formula_is_written_as_text` (asserts no `<f>` in the sheet XML) and `test_control_characters_are_dropped_not_fatal`. |
| 5 | **Imported open items show in the reviewer queue.** `list_items`'s default queue adds the queue statuses but doesn't exclude legacy, while `queue_stats` does. The sample adds 16 unreviewable rows, and the list and the stats strip disagree. | Fixed in `reviews/selectors.py` (E's file; minimal, flagged in the PR): the implicit queue (sort=queue, no status filter) adds `is_legacy=False` unless the caller set `is_legacy`. `imports/tests/test_api.py::test_imported_open_items_stay_out_of_the_review_queue` checks that the queue shows only the real item, `?is_legacy=true` shows the 16, and stats open = 1. |
| 6 | **Evidence packs could hand marketers partner attachments.** `DecisionEvidence` can point at any attachment, and marketers can request packs. The ledger ruling restricts partner attachments to reviewer, lead, and admin (latent; depends on E). | Fixed: `write_evidence_pack(..., partner_files=)`. For a requester without reviewer or admin, partner-owned evidence is listed in the manifest with its decision-time hash and `withheld`, but its file is left out, and the summary says so. Test: `test_partner_documents_are_withheld_from_a_marketers_pack` (the reviewer's pack includes the file; the marketer's pack still passes SHA256SUMS). |
| 7 | **An export killed mid-build stays `running` forever.** A redelivered message skips it because it isn't pending. An import hit the same way shows no error until someone re-POSTs commit. | Fixed: both tasks have `soft_time_limit=270`, under the 300 s hard limit, so a slow job fails visibly. `run_export` reclaims a `running` job whose `started_at` is older than the hard limit + 60 s, so the acks-late redelivery after a worker crash finishes it. A killed import already self-heals: its transaction rolls back, the job stays `committing`, and the redelivered task commits. Test: `test_a_running_export_whose_worker_died_is_reclaimed`. Remaining gap: if no redelivery happens, the UI shows `running` until the user retries. Noted in the report. |

## Minor

| # | Finding | Resolution |
|---|---|---|
| 8 | Job errors were raw exception text (multi-line SQL detail, a doubled period, the wrong advice), plus "1 rows have problems." | Fixed: domain errors store their own one-line message. Anything else stores "The commit failed and nothing was imported. Try again; if it fails again, report import N." or "The export failed. Request it again; if it fails again, report export N." The exception is logged, not shown. Pluralization is shared in `_blocked_message`. The tests assert the exact strings. |
| 9 | A mapping PUT with only columns erased the saved status and value mappings. | Fixed: `status_values` and `value_mappings` are optional, and omitting them (or sending null) keeps what's saved (`services.MappingUpdate`). Test: `test_a_columns_only_update_keeps_saved_status_and_value_mappings`. |
| 10 | Two columns mapped to one field were silently accepted. | Fixed: `set_mapping` refuses with "Status is mapped from both 'Revision Round' and 'Status'; set one to Ignore." Test: `test_two_columns_can_not_map_to_one_field`. |
| 11 | The ref pattern is looser than the README's, so a stray `179` becomes a blocked data row instead of a non-data row. | Partly changed: a ref-shaped cell on a row where every other required column is blank is a non-data row (`test_a_ref_shaped_cell_on_an_otherwise_blank_row_is_not_data`). The broader pattern stays, so other trackers' IDs import; it's recorded as a deviation. |
| 12 | A ref reused across two imports is skipped as already imported, even if the second file's row is a different asset. | Kept and documented as a limitation in the report. The (title, date) discriminator works within one sheet. Across imports, the `-b` suffix depends on sheet position, so comparing against the stored item would still need a rule for which suffix the newcomer gets. |
| 13a | A one-character prefix matches a partner (`R` → RateRadar). | Fixed: a prefix match needs at least 4 characters (`test_partner_prefix_needs_four_characters`). |
| 13b | A date serial in a General-format cell (e.g. 46023) is a blocking "isn't a date". | Fixed: numbers 20000–80000 (1954–2119) convert with `from_excel`, as an info-level coerced date (`test_a_date_serial_in_a_general_cell_is_a_date`). |
| 13c | `javascript:` or `file:` hyperlinks are stored as `source_url`. | Fixed: only http(s) hyperlinks are kept, for both asset and placement (`test_only_web_links_are_kept`). |
| 13d | Approvers resolve only against the Lists sheet, so a tracker without one warns on every approved row. | Fixed: falls back to the names in the Reviewer column (`test_approvers_resolve_from_the_reviewer_column_without_a_lists_sheet`). |
| 14a | `exports/selectors.py` duplicates the queue sort keys and the implicit queue-status rule. | Not changed: `reviews.selectors._SORTS` is private and keyed for keyset pagination. Noted as drift risk in the report. A public `order_items(qs, sort)` in reviews would remove the copy (E's file). |
| 14b | `EXPORT_CREATED` records only export id and count, not filters or kind. | Not changed: the payload model is in `audit.payloads` (not G's). The job row keeps `filters`, `sort`, `kind`, and `created_by`, and the event's `entity_id` points at it. Noted in the report. |
| 14c | `InvalidInput` field paths came out as one dotted string. | Fixed: the import mapping errors use segmented locs (`["body", "value_mappings", 0, "value"]`), as ninja does. |
| 14d | GET evidence-pack checked only for a session while POST required a role. | Fixed: both go through a role check (`evidence.evidence_record`). |
| 14e | Deviation to record: GET evidence-pack returns JSON and the zip is a POST job. | Recorded in the report's Deviations. |

## Checked and fine (reviewer)

Oracle fidelity: the tests read the README itself and the hard-coded totals are pinned to its text. Problem
counts on the sample match the README. Date parsing and year rollover are right. Commit uses a row lock, an
advisory lock, and a fresh evaluate, with no-op re-commits and a working rollback and retry. The events and
their transactions are right. Download authorization holds: another user's export is 404, an admin can
download, and an export that isn't ready is 409. The stored names are random and nothing goes through a media
URL. SHA256SUMS is in the right format.
