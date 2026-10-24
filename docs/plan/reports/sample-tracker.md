# Report: sample legacy tracker (workstream B)

## What was produced

| Path | What |
|---|---|
| `scripts/generate_sample_tracker.py` | Standalone PEP 723 script (`openpyxl>=3.1.5`), run with `uv run scripts/generate_sample_tracker.py`. One `random.Random(20251101)` drives everything. It simulates each request's review (reviewer assignment, rounds, waits, outcome), renders the rows, applies the intended mess, writes the workbook, and **generates** `samples/README.md` from the same records. |
| `samples/clearpath_review_tracker.xlsx` | 3 sheets. `Review Tracker`: 17 columns, 180 rows below the header (178 items, 1 exact duplicate row, 1 merged note row), submitted 2025-11-03 to 2026-10-20, last touched 2026-10-23. `Lists`: the dropdown values. `Partners`: 8 partners. |
| `samples/README.md` | The import oracle: column semantics, comment grammar, expected totals, every messy cell (kind, Request ID, Excel row, exact raw value, expected result), an exhaustive raw-to-canonical table for Status / Product / Trigger / Partner, and the non-error traits that change metrics. |

**Content.** Six marketers in six BUs, four reviewers plus a lead (Nikhil Rao joins 3/2/26, which adds capacity mid-year), and eight partners: two comparison marketplaces, a card rewards blog, an influencer, two lead-gen shops, a loan marketplace, and a CA finance blog. Reviewer comments are drawn from a catalogue of about 40 findings built from the regulations rule-check table:
- "as low as" without range + creditworthiness qualifier
- trigger terms needing the rep example ($10,000 / 36 mo / 12.99% = $337/mo, $12,128 total; I checked the math)
- CFL license line
- card issuer line for the invented sponsor bank (Harborview Bank, N.A.)
- intro APR wording
- prescreen notices
- NMLS / CRMLA
- FHA/government imagery
- SMS consent and STOP
- CAN-SPAM footer
- `#ad` on partner copy
- Reg B imagery flags, citing the 7/21/26 rewrite after that date
- stale 8.99% floor after the 6/1/26 rate-sheet change

Wait time to first review grows with volume. The result is revision rounds {1: 67, 2: 66, 3: 37, 4: 7, 5: 2}; on 10/23 there are 16 open items (8 unassigned) and 11 changes-requested items, some of them stale for months.

## Verification (commands and actual output)

Determinism: generate, copy, generate again, then hash every cell of both files as `(coordinate, repr(value), data_type, number_format, hyperlink target)`, plus merges, conditional formats and data validations. The checker is `verify.py` in the session scratchpad; it isn't committed.

```
$ uv run scripts/generate_sample_tracker.py   # twice, copying run 1 aside
content sha256: 8e740580668894b32457065902fd7cc5654c6dfc831b43dab62acba1a4274537   (run 1)
content sha256: 8e740580668894b32457065902fd7cc5654c6dfc831b43dab62acba1a4274537   (run 2)
$ cmp run1.md samples/README.md && echo README-identical
README-identical
```

Lint and types:

```
$ cd backend && uv run --group lint ruff check ../scripts
All checks passed!
$ uv run --group lint ruff format --check ../scripts
1 file already formatted
$ uv run --group typecheck --with openpyxl --with types-openpyxl pyrefly check --config pyproject.toml ../scripts/generate_sample_tracker.py
 INFO 0 errors
```

Summary of the committed workbook, read back with openpyxl:

```
sheets: ['Review Tracker', 'Lists', 'Partners']
columns: 17
max_row: 181 data rows below header: 180
merged: ['A19:Q19']
rows with Request ID: 179 non-ID rows: 1
duplicated IDs: {'MCR-26-045': 2, 'MCR-26-101': 2}
statuses: {"'Approved - minor edits'": 4, "'Approved w/ Changes'": 6, "'Approved w/ changes'": 3, "'Approved'": 128,
  "'Changes Req.'": 3, "'Changes Requested'": 5, "'In Review'": 5, "'Needs changes'": 3, "'Not Started'": 2,
  "'Pending'": 3, "'Rejected'": 6, "'approved '": 4, "'in review'": 3, 'None': 4}
products: {"' Credit Card'": 1, "'CC'": 10, "'Credit Card'": 54, "'MTG'": 6, "'Mortgage Prequal'": 26, "'PL'": 14,
  "'Personal Loan'": 64, "'personal loans'": 4}
trigger Y/N: {"'?'": 3, "'N'": 105, "'Y'": 61, "'yes'": 5, 'None': 5}
Date Submitted types: {'datetime': 164, 'str': 15}
Expiration types: {'datetime': 137, 'empty': 39, 'str': 3}
Date Submitted range (real dates): 2025-11-03 to 2026-10-20
real-date submissions per month: {'2025-11': 7, '2025-12': 8, '2026-01': 10, '2026-02': 11, '2026-03': 12,
  '2026-04': 14, '2026-05': 16, '2026-06': 13, '2026-07': 16, '2026-08': 16, '2026-09': 20, '2026-10': 21}
hyperlinks in Asset Name / File Link: 112
hyperlinks in Live URL / Placement & Screenshot Link: 23
revision rounds: {1: 67, 2: 66, 3: 37, 4: 7, 5: 2}
unassigned: 8
conditional formats: ['M2:M181']
data validations: [('M2:M181', '=Lists!$A$2:$A$7'), ('D2:D181', '=Lists!$B$2:$B$4'), ('E2:E181', '=Lists!$C$2:$C$10'),
  ('H2:H181', '=Lists!$D$2:$D$4'), ('I2:I181', '=Lists!$E$2:$E$3'), ('J2:J181', '=Lists!$F$2:$F$6')]
Partners rows: 8 Lists cols: 7
```

The per-month counts cover real-date cells only; the 15 text-date rows are missing from them.

Two independent checkers (also in the scratchpad) re-parse the xlsx the way an importer would, then compare it with the README:

```
consistency.py: checked rows: 179, problems: 0
readme_check.py: inline refs checked: 478; oracle table rows checked: 119 mismatches: 0
```

`consistency.py` checks the following:
- comment segments parse and are numbered 1..n
- comment dates are monotonic once the year rollover is applied
- no comment is dated inside the holiday freeze
- Revision Round is the segment count, or count + 1 only on in-review rows
- Version # is the round, or round + 1
- the approval date and approver match the last segment
- every partner variant resolves, and no partner row predates that partner's agreement date

`readme_check.py` checks that every `MCR-.. (rN)` reference points at that ID in that row, and that every Raw value in the oracle tables equals the actual cell.

## What importer authors must know

1. **The README is generated.** Edit the script and regenerate; hand edits are overwritten. Row numbers in it are exact for the committed file.
2. **Canonical values are the `backend/core/domain.py` enums** (main @ `8dc4e81`): `personal_loan` / `credit_card` / `mortgage_prequal`, snake_case channels, lowercase risk tiers, `approved_with_edits`, and `PartnerType.influencer`, which is Money with Maya's type. The README has a label-to-enum section.
3. **Blank means `None`.** openpyxl drops empty strings, so blank Status and Y/N cells read as `None`. Real dates load as `datetime` at midnight, not `date`.
4. **Take the outcome from Status, never from comment text.** Findings quote copy such as `'You're pre-approved!'`, so searching comment text for "approved" misclassifies rounds. Comments supply only the round count, dates and reviewer initials.
5. **Year inference is required in two places:** comment dates (`R2 1/9 LB:`) roll over from the submission year, and four Date Submitted cells are `Mon D`, whose year comes from the `MCR-YY-` prefix.
6. **Duplicate vs reused ID.** The discriminator is (Asset Name, Date Submitted). MCR-26-045 (r64, r68) is an exact copy, so import it once. MCR-26-101 (r121, r122) is two different assets, so import both and give the later row a disambiguated `legacy_ref` (README suggests `-b`). `legacy_ref` is unique, so this has to be decided.
7. **Past-expiry approvals import as `approved`**, not `needs_rereview` or `expired`. Spec §4.2.7 excludes legacy items from the expiry sweep. I first had needs_rereview/expired expectations and dropped them after reading the spec. The README lists those rows as information only.
8. **Rules the README prescribes that are my judgment, so attack them if you disagree:**
   - Partner matching uses a casefolded alphanumeric key plus unique-prefix fallback; that's how `CardPerks` resolves to `CardPerks Weekly`.
   - Y/N blank and `?` are stored as null with a warning, not inferred from comments.
   - A blank Status is inferred as approved only when the Approval cell is filled (MCR-26-015, r34); otherwise it's submitted.
   - A blank expiry stays null with no policy default applied.
9. **Risk Tier follows the spec §4.2.5 derivation.** I treated every Direct Mail piece as high-risk because it stands in for "prescreen"; the data has no explicit prescreen flag.
10. **Determinism is content-level, not byte-level.** openpyxl stamps `docProps/core.xml` `dcterms:modified` with the save time, overwriting any pinned value. I checked this: run 1 had `2026-10-24T12:18:39Z`. It also stamps zip entry times. File bytes therefore change from run to run, and a regenerate always produces a binary diff in git. Compare cell content, as `verify.py` does, not file hashes.
11. **CI doesn't cover `scripts/`.** `backend-ci.yaml` is path-filtered to `backend/**` and runs `ruff check .` inside `backend/`, so this PR triggers no lint job. The ruff and pyrefly results above are local runs only.
12. Everything external uses the reserved `.example` TLD (partner sites, contact emails, SharePoint, the ClearPath site). The license and NMLS numbers are invented.
