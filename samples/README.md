# Sample legacy review tracker

`clearpath_review_tracker.xlsx` is the fictional Excel tracker ClearPath's compliance team used before the
tool: one row per review request, redlines typed into one cell, approvals buried in email. The Import page
ingests it ("Load sample tracker") to prove migration works, and its history seeds queue and metrics data.

**Generated, not hand-edited.** `uv run scripts/generate_sample_tracker.py` rewrites both this README and
the workbook from one seeded RNG; re-running produces identical cell values. Change the script, then
regenerate. Every row number and Request ID below is computed from the same data the workbook is written
from, so this file is the test oracle for the importer (spec 4.3, Import: "Every intended mess listed in
`samples/README.md` is handled as specified there").

Everything is fictional. Domains use the reserved `.example` TLD; the sponsor bank (Harborview Bank, N.A.),
license and NMLS numbers are invented.

## Sheets

| Sheet | Contents |
|---|---|
| `Review Tracker` | Header in row 1 (frozen, autofiltered, dark fill). One row per request, plus one merged note row and one pasted duplicate (see below). Status is colour-coded with `SEARCH()`-based conditional formats, so misspelled statuses still colour. Data validation dropdowns point at `Lists` but have `showErrorMessage=False`, so off-list values were accepted. |
| `Lists` | The dropdown values the team *intended* to use: Status, Product, Channel, Risk Tier, Y/N, Reviewer, Business Unit. The data does not always follow them. |
| `Partners` | Partner name, type, description, contact email, agreement date, status, notes. Names here are canonical. |

## Column semantics (clean case)

| Column | Meaning when clean |
|---|---|
| Request ID | `MCR-YY-NNN`, numbered per year in submission order (regex `^MCR-\d{2}-\d{3}$` after strip). Becomes `legacy_ref`; it is not the app's `CP-####` display ID. |
| Date Submitted | A real Excel date (`m/d/yyyy` format; openpyxl loads it as a `datetime` at midnight). Exceptions below. |
| Submitter / BU | `First Last / Business Unit`. |
| Product | A `Lists` label (`Personal Loan`, `Credit Card`, `Mortgage Prequal`); app values below. |
| Channel | One of the nine `Lists` channels. |
| Asset Name / File Link | One of three shapes: a hyperlinked file name (target = SharePoint URL), `<asset name> - <SharePoint URL>` as text, or `<asset name> (emailed M/D)` with no link at all. |
| Affiliate / Partner | Blank for first-party assets, else a Partners-sheet name. |
| Risk Tier | `High` / `Medium` / `Low`, following the app's intake derivation: partner, mortgage and direct mail high; paid ads and LPs medium; the rest low; no-offer brand assets low. |
| Trigger Terms Present (Y/N) | `Y` / `N`: whether the copy contains a Reg Z trigger term. |
| Assigned Reviewer | Full name from `Lists`; blank when nobody has picked the item up. |
| Version # | Latest version the marketer sent. Equals Revision Round, except where the marketer sent v2 before the first review (listed below). |
| Revision Round | Current or last review round, starting at 1. Equals the number of comment segments, or that plus 1 when the item was resubmitted and the new round has not been reviewed yet (status In Review). Unreviewed items have round 1 and no comments. |
| Status | A `Lists` status; mapping in "Status values" below. The outcome comes from here, not from Comments. |
| Reviewer Comments / Required Changes | Every round in one cell; grammar below. Blank when no review has happened yet. |
| Approval Date & Approver | `M/D/YY - F. Last` on approved rows, blank otherwise. The date equals the last comment segment's date and the approver is that segment's reviewer. |
| Approval Expiration / Re-review Date | Real Excel date. The policy the team followed: one-off sends (Email, SMS, Direct Mail) = end of the send window, 14-45 days after approval; Landing Page and Call Script = 12 months; Affiliate Page, Paid Social, Paid Search and Display = 6 months. |
| Live URL / Placement & Screenshot Link | Blank, a hyperlink (target = placement URL; display text is the URL or a friendly label), a plain-text URL, or a placement description (`Sent 3/18 to ...`, `Drop 4/2, 48k pieces`, `Meta campaign ...`, `IG post @moneywithmaya 2/14`, `Live in call center KB-1234`). Text cells may end in `; screenshot: <url>`. |

### Comment grammar

Each round is one segment: `R<n> <M>/<D> <II>: <text>`. Segments are separated by a single space or by a
newline (Alt+Enter) depending on who typed them; both appear. Parse with

```
R(?P<round>\d+) (?P<month>\d{1,2})/(?P<day>\d{1,2}) (?P<initials>[A-Z]{2}):
```

and split on the match starts; segment text never contains that pattern. Dates have no year: start from
the Date Submitted year and add one each time the month goes backwards (rows that cross New Year are listed
below). Initials are unique: DK Dana Kim, SO Samuel Ortega, LB Leah Brandt, NR Nikhil Rao (joined 3/2/26),
RO Rachel Okafor (compliance lead). On decided rows the last segment is the decision round (its date is the
decision date); every earlier segment requested changes. Do not classify segments by searching for
"approved": findings quote copy such as 'You're pre-approved!'. Take the outcome from Status.

## Expected import totals

- Sheet rows below the header: 180 (r2-r181).
- Data rows with a Request ID: 179; note rows: 1; exact duplicates to drop: 1.
- **Items after import: 178**, with 177 distinct Request IDs (one ID is shared by two items).
- Submitted 2025-11-03 to 2026-10-20; the tracker was last updated 2026-10-23.
- Open (submitted or in review) on 2026-10-23: 16; unassigned: 8.

| Canonical status | Items |
|---|---|
| approved (decision: approved) | 132 |
| approved (decision: approved_with_edits) | 13 |
| changes_requested | 11 |
| in_review | 8 |
| rejected (decision: rejected) | 6 |
| submitted | 8 |

## Intended messiness (the oracle)

Each kind lists every affected cell. `rN` is the Excel row number. Values in backticks are exact, including spaces; `(empty)` is an empty cell. 'Importer should' is the required behaviour.

### Status spelling variants

Importer should: Map case- and whitespace-insensitively through the status table below. A blank Status is approved (decision approved, with a warning) when the Approval cell is filled, otherwise submitted. Values outside the table are a preview problem, not a guess.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-009 | r28 | Status | `"Approved w/ changes"` | approved (decision: approved_with_edits) |
| MCR-26-013 | r32 | Status | `"approved "` | approved (decision: approved) |
| MCR-26-015 | r34 | Status | `(empty)` | approved (decision: approved) - inferred from the filled Approval cell; emit a warning |
| MCR-26-042 | r61 | Status | `"approved "` | approved (decision: approved) |
| MCR-26-046 | r65 | Status | `"Needs changes"` | changes_requested |
| MCR-26-063 | r83 | Status | `"approved "` | approved (decision: approved) |
| MCR-26-064 | r84 | Status | `"Approved w/ changes"` | approved (decision: approved_with_edits) |
| MCR-26-072 | r92 | Status | `"Changes Req."` | changes_requested |
| MCR-26-073 | r93 | Status | `"Approved w/ changes"` | approved (decision: approved_with_edits) |
| MCR-26-091 | r111 | Status | `"Approved - minor edits"` | approved (decision: approved_with_edits) |
| MCR-26-092 | r112 | Status | `"Approved - minor edits"` | approved (decision: approved_with_edits) |
| MCR-26-094 | r114 | Status | `"Approved - minor edits"` | approved (decision: approved_with_edits) |
| MCR-26-100 | r120 | Status | `"approved "` | approved (decision: approved) |
| MCR-26-123 | r144 | Status | `"Approved - minor edits"` | approved (decision: approved_with_edits) |
| MCR-26-130 | r151 | Status | `"in review"` | in_review |
| MCR-26-138 | r159 | Status | `"Changes Req."` | changes_requested |
| MCR-26-139 | r160 | Status | `"Changes Req."` | changes_requested |
| MCR-26-143 | r164 | Status | `"in review"` | in_review |
| MCR-26-147 | r168 | Status | `"in review"` | in_review |
| MCR-26-148 | r169 | Status | `"Needs changes"` | changes_requested |
| MCR-26-150 | r171 | Status | `"Needs changes"` | changes_requested |
| MCR-26-151 | r172 | Status | `"Pending"` | submitted |
| MCR-26-154 | r175 | Status | `(empty)` | submitted |
| MCR-26-155 | r176 | Status | `(empty)` | submitted |
| MCR-26-156 | r177 | Status | `(empty)` | submitted |
| MCR-26-159 | r180 | Status | `"Pending"` | submitted |
| MCR-26-160 | r181 | Status | `"Pending"` | submitted |

### Product spelling variants

Importer should: Strip, then map case-insensitively: PL / Personal Loan / personal loans -> personal_loan, CC / Credit Card -> credit_card, MTG / Mortgage Prequal -> mortgage_prequal.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-004 | r5 | Product | `"personal loans"` | personal_loan |
| MCR-25-007 | r8 | Product | `"personal loans"` | personal_loan |
| MCR-25-012 | r13 | Product | `"MTG"` | mortgage_prequal |
| MCR-25-016 | r17 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-005 | r24 | Product | `"PL"` | personal_loan |
| MCR-26-006 | r25 | Product | `"PL"` | personal_loan |
| MCR-26-009 | r28 | Product | `"personal loans"` | personal_loan |
| MCR-26-017 | r36 | Product | `"CC"` | credit_card |
| MCR-26-020 | r39 | Product | `"CC"` | credit_card |
| MCR-26-025 | r44 | Product | `"PL"` | personal_loan |
| MCR-26-046 | r65 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-052 | r72 | Product | `"personal loans"` | personal_loan |
| MCR-26-054 | r74 | Product | `"PL"` | personal_loan |
| MCR-26-058 | r78 | Product | `"CC"` | credit_card |
| MCR-26-062 | r82 | Product | `"PL"` | personal_loan |
| MCR-26-065 | r85 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-070 | r90 | Product | `"CC"` | credit_card |
| MCR-26-087 | r107 | Product | `"PL"` | personal_loan |
| MCR-26-100 | r120 | Product | `"PL"` | personal_loan |
| MCR-26-105 | r126 | Product | `"PL"` | personal_loan |
| MCR-26-107 | r128 | Product | `"PL"` | personal_loan |
| MCR-26-108 | r129 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-109 | r130 | Product | `"CC"` | credit_card |
| MCR-26-111 | r132 | Product | `"CC"` | credit_card |
| MCR-26-113 | r134 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-119 | r140 | Product | `"CC"` | credit_card |
| MCR-26-124 | r145 | Product | `"PL"` | personal_loan |
| MCR-26-129 | r150 | Product | `"CC"` | credit_card |
| MCR-26-141 | r162 | Product | `"CC"` | credit_card |
| MCR-26-142 | r163 | Product | `"PL"` | personal_loan |
| MCR-26-144 | r165 | Product | `"PL"` | personal_loan |
| MCR-26-145 | r166 | Product | `"CC"` | credit_card |
| MCR-26-152 | r173 | Product | `"PL"` | personal_loan |
| MCR-26-156 | r177 | Product | `"PL"` | personal_loan |

### Date Submitted stored as text

Importer should: Accept real dates, `M/D/YY` (US order, 20YY), ISO `YYYY-MM-DD`, and `Mon D` with the year taken from the Request ID prefix. Report each coerced cell as an info-level note.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-005 | r6 | Date Submitted | `"11/19/25"` | 2025-11-19 |
| MCR-25-010 | r11 | Date Submitted | `"Dec 1"` | 2025-12-01 (year from the MCR-YY- prefix) |
| MCR-26-011 | r30 | Date Submitted | `"Jan 28"` | 2026-01-28 (year from the MCR-YY- prefix) |
| MCR-26-023 | r42 | Date Submitted | `"2/24/26"` | 2026-02-24 |
| MCR-26-031 | r50 | Date Submitted | `"2026-03-16"` | 2026-03-16 |
| MCR-26-035 | r54 | Date Submitted | `"Mar 25"` | 2026-03-25 (year from the MCR-YY- prefix) |
| MCR-26-046 | r65 | Date Submitted | `"4/20/26"` | 2026-04-20 |
| MCR-26-071 | r91 | Date Submitted | `"6/8/26"` | 2026-06-08 |
| MCR-26-073 | r93 | Date Submitted | `"2026-06-09"` | 2026-06-09 |
| MCR-26-074 | r94 | Date Submitted | `"2026-06-11"` | 2026-06-11 |
| MCR-26-078 | r98 | Date Submitted | `"Jun 17"` | 2026-06-17 (year from the MCR-YY- prefix) |
| MCR-26-098 | r118 | Date Submitted | `"7/28/26"` | 2026-07-28 |
| MCR-26-106 | r127 | Date Submitted | `"2026-08-06"` | 2026-08-06 |
| MCR-26-113 | r134 | Date Submitted | `"8/19/26"` | 2026-08-19 |
| MCR-26-152 | r173 | Date Submitted | `"2026-10-14"` | 2026-10-14 |

### Expiration stored as text

Importer should: Same parser as Date Submitted (`M/D/YY` text).

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-015 | r34 | Approval Expiration / Re-review Date | `"3/12/26"` | 2026-03-12 |
| MCR-26-099 | r119 | Approval Expiration / Re-review Date | `"9/9/26"` | 2026-09-09 |
| MCR-26-112 | r133 | Approval Expiration / Re-review Date | `"3/21/27"` | 2027-03-21 |

### Approval cell with approver only (no date)

Importer should: Approver resolved from `F. Last` to the reviewer; approval date taken from the final comment segment (and flagged as derived).

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-012 | r13 | Approval Date & Approver | `"L. Brandt"` | approver Leah Brandt; date 2026-01-15 from the last R-segment in Comments |
| MCR-26-023 | r42 | Approval Date & Approver | `"L. Brandt"` | approver Leah Brandt; date 2026-03-13 from the last R-segment in Comments |
| MCR-26-033 | r52 | Approval Date & Approver | `"N. Rao"` | approver Nikhil Rao; date 2026-04-07 from the last R-segment in Comments |
| MCR-26-074 | r94 | Approval Date & Approver | `"R. Okafor"` | approver Rachel Okafor; date 2026-07-23 from the last R-segment in Comments |
| MCR-26-107 | r128 | Approval Date & Approver | `"D. Kim"` | approver Dana Kim; date 2026-08-28 from the last R-segment in Comments |
| MCR-26-136 | r157 | Approval Date & Approver | `"S. Ortega"` | approver Samuel Ortega; date 2026-10-20 from the last R-segment in Comments |

### Approved row with blank expiration

Importer should: Store `expires_at` null and report it. Do not invent a date (the generator's policy default is shown only so tests can tell the rows apart).

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-004 | r5 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2026-05-24) |
| MCR-25-012 | r13 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2027-01-15) |
| MCR-26-030 | r49 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2026-10-07) |
| MCR-26-070 | r90 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2027-01-01) |
| MCR-26-104 | r125 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2027-03-03) |
| MCR-26-118 | r139 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2026-11-07) |

### Exact duplicate row

Importer should: Rows identical in every cell are one item.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-045 | r64, r68 | (whole row) | `every cell identical, including hyperlinks` | import one item; report the second row as a duplicate and skip it |

### Request ID reused for a different asset

Importer should: Same Request ID, different Asset Name / Date Submitted: two items. The discriminator is (Asset Name, Date Submitted); identical values mean duplicate, different mean reuse.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-101 | r121, r122 | Request ID | `"MCR-26-101"` | two items: r121 'CC Double Points email' (submitted 2026-07-30) and r122 'CC 0% Intro APR LP' (submitted 2026-08-04). Import both; the later row gets a disambiguated legacy_ref (e.g. MCR-26-101-b) and an admin warning |

### Leading / trailing whitespace

Importer should: Strip every string cell before matching or storing.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-030 | r49 | Affiliate / Partner | `" Money with Maya "` | "Money with Maya" after strip() |
| MCR-26-035 | r54 | Assigned Reviewer | `"Rachel Okafor "` | "Rachel Okafor" after strip() |
| MCR-26-049 | r69 | Affiliate / Partner | `" FinMatch "` | "FinMatch" after strip() |
| MCR-26-063 | r83 | Product | `" Credit Card"` | "Credit Card" after strip() |
| MCR-26-077 | r97 | Assigned Reviewer | `"Rachel Okafor "` | "Rachel Okafor" after strip() |
| MCR-26-077 | r97 | Submitter / BU | `"Marcus Bell / Card Marketing  "` | "Marcus Bell / Card Marketing" after strip() |
| MCR-26-091 | r111 | Channel | `"Paid Social "` | "Paid Social" after strip() |
| MCR-26-095 | r115 | Submitter / BU | `"Marcus Bell / Card Marketing  "` | "Marcus Bell / Card Marketing" after strip() |
| MCR-26-129 | r150 | Request ID | `"MCR-26-129 "` | "MCR-26-129" after strip() |

### Partner typed differently from the Partners sheet

Importer should: Match partners by a normalized key (casefold, drop spaces and punctuation) against the Partners sheet; the bare `CardPerks` resolves to `CardPerks Weekly` because it is a unique prefix. Report each fuzzy match.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-022 | r41 | Affiliate / Partner | `"Lend Compare"` | partner 'LendCompare' |
| MCR-26-050 | r70 | Affiliate / Partner | `"CardPerks"` | partner 'CardPerks Weekly' |
| MCR-26-054 | r74 | Affiliate / Partner | `"Leadstream Direct"` | partner 'LeadStream Direct' |
| MCR-26-136 | r157 | Affiliate / Partner | `"Lend Compare"` | partner 'LendCompare' |

### Trigger Terms Y/N variants

Importer should: `Y`/`yes` -> true, `N` -> false, blank or `?` -> null with a warning. Do not infer from comments.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-016 | r35 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was N |
| MCR-26-032 | r51 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-040 | r59 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was N |
| MCR-26-041 | r60 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-062 | r82 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was N |
| MCR-26-091 | r111 | Trigger Terms Present (Y/N) | `"?"` | null (unknown) + warning; generator truth was N |
| MCR-26-096 | r116 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-116 | r137 | Trigger Terms Present (Y/N) | `"?"` | null (unknown) + warning; generator truth was N |
| MCR-26-119 | r140 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-136 | r157 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-139 | r160 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was N |
| MCR-26-141 | r162 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was Y |
| MCR-26-147 | r168 | Trigger Terms Present (Y/N) | `"?"` | null (unknown) + warning; generator truth was N |

### Merged note row inside the data

Importer should: Skip rows whose stripped column A does not match the Request ID pattern; report them.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| (none) | r19 | A19:Q19 merged | `"NOTE (R. Okafor 1/5/26): holiday review freeze 12/22 - 1/2, ..."` | skip: column A does not match the Request ID pattern; report it as a skipped non-data row |

### Links: hyperlink objects vs text

Importer should: read `cell.hyperlink.target` when a hyperlink exists (the display text may be a label such as `LendCompare listing`), otherwise extract URLs from the text with a regex. Hyperlinked cells:

- **Asset Name / File Link**: 112 hyperlinked cells: MCR-25-003 (r4), MCR-25-007 (r8), MCR-25-008 (r9), MCR-25-013 (r14), MCR-25-016 (r17), MCR-26-005 (r24), MCR-26-012 (r31), MCR-26-013 (r32), MCR-26-014 (r33), MCR-26-015 (r34), MCR-26-018 (r37), MCR-26-019 (r38), MCR-26-021 (r40), MCR-26-022 (r41), MCR-26-024 (r43), MCR-26-025 (r44), MCR-26-026 (r45), MCR-26-030 (r49), MCR-26-031 (r50), MCR-26-034 (r53), MCR-26-035 (r54), MCR-26-036 (r55), MCR-26-037 (r56), MCR-26-038 (r57), MCR-26-039 (r58), MCR-26-040 (r59), MCR-26-041 (r60), MCR-26-042 (r61), MCR-26-043 (r62), MCR-26-044 (r63), MCR-26-048 (r67), MCR-26-049 (r69), MCR-26-050 (r70), MCR-26-055 (r75), MCR-26-056 (r76), MCR-26-057 (r77), MCR-26-058 (r78), MCR-26-059 (r79), MCR-26-061 (r81), MCR-26-062 (r82), MCR-26-063 (r83), MCR-26-064 (r84), MCR-26-065 (r85), MCR-26-066 (r86), MCR-26-067 (r87), MCR-26-069 (r89), MCR-26-071 (r91), MCR-26-072 (r92), MCR-26-073 (r93), MCR-26-075 (r95), MCR-26-076 (r96), MCR-26-077 (r97), MCR-26-078 (r98), MCR-26-079 (r99), MCR-26-081 (r101), MCR-26-082 (r102), MCR-26-084 (r104), MCR-26-086 (r106), MCR-26-087 (r107), MCR-26-088 (r108), MCR-26-089 (r109), MCR-26-090 (r110), MCR-26-091 (r111), MCR-26-092 (r112), MCR-26-093 (r113), MCR-26-094 (r114), MCR-26-097 (r117), MCR-26-098 (r118), MCR-26-099 (r119), MCR-26-100 (r120), MCR-26-101 (r121), MCR-26-101 (r122), MCR-26-103 (r124), MCR-26-104 (r125), MCR-26-105 (r126), MCR-26-106 (r127), MCR-26-107 (r128), MCR-26-108 (r129), MCR-26-110 (r131), MCR-26-111 (r132), MCR-26-112 (r133), MCR-26-113 (r134), MCR-26-115 (r136), MCR-26-116 (r137), MCR-26-118 (r139), MCR-26-119 (r140), MCR-26-120 (r141), MCR-26-121 (r142), MCR-26-122 (r143), MCR-26-125 (r146), MCR-26-133 (r154), MCR-26-134 (r155), MCR-26-135 (r156), MCR-26-136 (r157), MCR-26-137 (r158), MCR-26-139 (r160), MCR-26-141 (r162), MCR-26-142 (r163), MCR-26-144 (r165), MCR-26-145 (r166), MCR-26-146 (r167), MCR-26-147 (r168), MCR-26-148 (r169), MCR-26-149 (r170), MCR-26-150 (r171), MCR-26-151 (r172), MCR-26-152 (r173), MCR-26-155 (r176), MCR-26-156 (r177), MCR-26-157 (r178), MCR-26-158 (r179), MCR-26-159 (r180).
  - Text containing a URL, no hyperlink object (45): MCR-25-001 (r2), MCR-25-002 (r3), MCR-25-005 (r6), MCR-25-006 (r7), MCR-25-009 (r10), MCR-25-010 (r11), MCR-25-011 (r12), MCR-25-012 (r13), MCR-25-014 (r15), MCR-25-015 (r16), MCR-25-017 (r18), MCR-26-001 (r20), MCR-26-004 (r23), MCR-26-006 (r25), MCR-26-007 (r26), MCR-26-008 (r27), MCR-26-009 (r28), MCR-26-011 (r30), MCR-26-017 (r36), MCR-26-023 (r42), MCR-26-028 (r47), MCR-26-029 (r48), MCR-26-032 (r51), MCR-26-033 (r52), MCR-26-046 (r65), MCR-26-047 (r66), MCR-26-052 (r72), MCR-26-054 (r74), MCR-26-070 (r90), MCR-26-074 (r94), MCR-26-080 (r100), MCR-26-096 (r116), MCR-26-102 (r123), MCR-26-109 (r130), MCR-26-114 (r135), MCR-26-117 (r138), MCR-26-123 (r144), MCR-26-124 (r145), MCR-26-128 (r149), MCR-26-129 (r150), MCR-26-132 (r153), MCR-26-138 (r159), MCR-26-153 (r174), MCR-26-154 (r175), MCR-26-160 (r181).
  - Asset name only, no link at all (22): MCR-25-004 (r5), MCR-26-002 (r21), MCR-26-003 (r22), MCR-26-010 (r29), MCR-26-016 (r35), MCR-26-020 (r39), MCR-26-027 (r46), MCR-26-045 (r64), MCR-26-045 (r68), MCR-26-051 (r71), MCR-26-053 (r73), MCR-26-060 (r80), MCR-26-068 (r88), MCR-26-083 (r103), MCR-26-085 (r105), MCR-26-095 (r115), MCR-26-126 (r147), MCR-26-127 (r148), MCR-26-130 (r151), MCR-26-131 (r152), MCR-26-140 (r161), MCR-26-143 (r164).
- **Live URL / Placement & Screenshot Link**: 23 hyperlinked cells: MCR-26-010 (r29), MCR-26-016 (r35), MCR-26-020 (r39), MCR-26-022 (r41), MCR-26-023 (r42), MCR-26-055 (r75), MCR-26-056 (r76), MCR-26-058 (r78), MCR-26-061 (r81), MCR-26-070 (r90), MCR-26-078 (r98), MCR-26-081 (r101), MCR-26-086 (r106), MCR-26-088 (r108), MCR-26-089 (r109), MCR-26-093 (r113), MCR-26-101 (r122), MCR-26-114 (r135), MCR-26-119 (r140), MCR-26-120 (r141), MCR-26-125 (r146), MCR-26-140 (r161), MCR-26-142 (r163).
  - Display text differs from the target (friendly label): MCR-26-016 (r35), MCR-26-020 (r39), MCR-26-055 (r75), MCR-26-070 (r90), MCR-26-081 (r101), MCR-26-088 (r108), MCR-26-089 (r109).
  - Text containing a URL, no hyperlink object (72): MCR-25-005 (r6), MCR-25-006 (r7), MCR-25-007 (r8), MCR-25-008 (r9), MCR-25-009 (r10), MCR-25-010 (r11), MCR-25-011 (r12), MCR-25-012 (r13), MCR-25-014 (r15), MCR-25-016 (r17), MCR-26-002 (r21), MCR-26-003 (r22), MCR-26-005 (r24), MCR-26-006 (r25), MCR-26-008 (r27), MCR-26-009 (r28), MCR-26-017 (r36), MCR-26-018 (r37), MCR-26-021 (r40), MCR-26-024 (r43), MCR-26-025 (r44), MCR-26-027 (r46), MCR-26-028 (r47), MCR-26-030 (r49), MCR-26-031 (r50), MCR-26-032 (r51), MCR-26-033 (r52), MCR-26-034 (r53), MCR-26-035 (r54), MCR-26-036 (r55), MCR-26-038 (r57), MCR-26-039 (r58), MCR-26-042 (r61), MCR-26-043 (r62), MCR-26-044 (r63), MCR-26-045 (r64), MCR-26-047 (r66), MCR-26-048 (r67), MCR-26-045 (r68), MCR-26-050 (r70), MCR-26-051 (r71), MCR-26-053 (r73), MCR-26-054 (r74), MCR-26-057 (r77), MCR-26-059 (r79), MCR-26-065 (r85), MCR-26-067 (r87), MCR-26-068 (r88), MCR-26-073 (r93), MCR-26-083 (r103), MCR-26-085 (r105), MCR-26-090 (r110), MCR-26-091 (r111), MCR-26-092 (r112), MCR-26-098 (r118), MCR-26-099 (r119), MCR-26-100 (r120), MCR-26-102 (r123), MCR-26-103 (r124), MCR-26-105 (r126), MCR-26-106 (r127), MCR-26-110 (r131), MCR-26-111 (r132), MCR-26-113 (r134), MCR-26-116 (r137), MCR-26-121 (r142), MCR-26-122 (r143), MCR-26-123 (r144), MCR-26-124 (r145), MCR-26-127 (r148), MCR-26-128 (r149), MCR-26-131 (r152).

## Every raw value, mapped

Exhaustive over all data rows (the duplicate row included). For Trigger Terms the Canonical column is the generator's truth; the importer must still store blank and `?` as null.

### Status values

| Raw cell | Canonical | Rows | Where (off-list values only) |
|---|---|---|---|
| `"Approved - minor edits"` | approved (decision: approved_with_edits) | 4 | MCR-26-091 (r111), MCR-26-092 (r112), MCR-26-094 (r114), MCR-26-123 (r144) |
| `"Approved w/ Changes"` | approved (decision: approved_with_edits) | 6 |  |
| `"Approved w/ changes"` | approved (decision: approved_with_edits) | 3 | MCR-26-009 (r28), MCR-26-064 (r84), MCR-26-073 (r93) |
| `"Approved"` | approved (decision: approved) | 128 |  |
| `"Changes Req."` | changes_requested | 3 | MCR-26-072 (r92), MCR-26-138 (r159), MCR-26-139 (r160) |
| `"Changes Requested"` | changes_requested | 5 |  |
| `"In Review"` | in_review | 5 |  |
| `"Needs changes"` | changes_requested | 3 | MCR-26-046 (r65), MCR-26-148 (r169), MCR-26-150 (r171) |
| `"Not Started"` | submitted | 2 |  |
| `"Pending"` | submitted | 3 | MCR-26-151 (r172), MCR-26-159 (r180), MCR-26-160 (r181) |
| `"Rejected"` | rejected (decision: rejected) | 6 |  |
| `"approved "` | approved (decision: approved) | 4 | MCR-26-013 (r32), MCR-26-042 (r61), MCR-26-063 (r83), MCR-26-100 (r120) |
| `"in review"` | in_review | 3 | MCR-26-130 (r151), MCR-26-143 (r164), MCR-26-147 (r168) |
| `(empty)` | approved (decision: approved) | 1 | MCR-26-015 (r34) |
| `(empty)` | submitted | 3 | MCR-26-154 (r175), MCR-26-155 (r176), MCR-26-156 (r177) |

### Product values

| Raw cell | Canonical | Rows | Where (off-list values only) |
|---|---|---|---|
| `" Credit Card"` | credit_card | 1 | MCR-26-063 (r83) |
| `"CC"` | credit_card | 10 | MCR-26-017 (r36), MCR-26-020 (r39), MCR-26-058 (r78), MCR-26-070 (r90), MCR-26-109 (r130), MCR-26-111 (r132), MCR-26-119 (r140), MCR-26-129 (r150), MCR-26-141 (r162), MCR-26-145 (r166) |
| `"Credit Card"` | credit_card | 54 |  |
| `"MTG"` | mortgage_prequal | 6 | MCR-25-012 (r13), MCR-25-016 (r17), MCR-26-046 (r65), MCR-26-065 (r85), MCR-26-108 (r129), MCR-26-113 (r134) |
| `"Mortgage Prequal"` | mortgage_prequal | 26 |  |
| `"PL"` | personal_loan | 14 | MCR-26-005 (r24), MCR-26-006 (r25), MCR-26-025 (r44), MCR-26-054 (r74), MCR-26-062 (r82), MCR-26-087 (r107), MCR-26-100 (r120), MCR-26-105 (r126), MCR-26-107 (r128), MCR-26-124 (r145), MCR-26-142 (r163), MCR-26-144 (r165), MCR-26-152 (r173), MCR-26-156 (r177) |
| `"Personal Loan"` | personal_loan | 64 |  |
| `"personal loans"` | personal_loan | 4 | MCR-25-004 (r5), MCR-25-007 (r8), MCR-26-009 (r28), MCR-26-052 (r72) |

### Trigger Terms values

| Raw cell | Canonical | Rows | Where (off-list values only) |
|---|---|---|---|
| `"?"` | N | 3 | MCR-26-091 (r111), MCR-26-116 (r137), MCR-26-147 (r168) |
| `"N"` | N | 105 |  |
| `"Y"` | Y | 61 |  |
| `"yes"` | Y | 5 | MCR-26-032 (r51), MCR-26-041 (r60), MCR-26-096 (r116), MCR-26-119 (r140), MCR-26-136 (r157) |
| `(empty)` | N | 4 | MCR-26-016 (r35), MCR-26-040 (r59), MCR-26-062 (r82), MCR-26-139 (r160) |
| `(empty)` | Y | 1 | MCR-26-141 (r162) |

### Partner values

| Raw cell | Canonical | Rows | Where (off-list values only) |
|---|---|---|---|
| `" FinMatch "` | FinMatch | 1 | MCR-26-049 (r69) |
| `" Money with Maya "` | Money with Maya | 1 | MCR-26-030 (r49) |
| `"CardPerks Weekly"` | CardPerks Weekly | 2 |  |
| `"CardPerks"` | CardPerks Weekly | 1 | MCR-26-050 (r70) |
| `"FinMatch"` | FinMatch | 4 |  |
| `"Golden State Saver"` | Golden State Saver | 3 |  |
| `"HomeBound Leads"` | HomeBound Leads | 2 |  |
| `"Leadstream Direct"` | LeadStream Direct | 1 | MCR-26-054 (r74) |
| `"Lend Compare"` | LendCompare | 2 | MCR-26-022 (r41), MCR-26-136 (r157) |
| `"LendCompare"` | LendCompare | 7 |  |
| `"Money with Maya"` | Money with Maya | 6 |  |
| `"RateRadar"` | RateRadar | 3 |  |
| `(empty)` | (none) | 146 |  |

### Clean labels to app vocabulary (`backend/core/domain.py`)

- Product: `Personal Loan` -> `personal_loan`, `Credit Card` -> `credit_card`, `Mortgage Prequal` -> `mortgage_prequal`.
- Channel: `Email` -> `email`, `Paid Social` -> `paid_social`, `Paid Search` -> `paid_search`, `Direct Mail` -> `direct_mail`, `Affiliate Page` -> `affiliate_page`, `SMS` -> `sms`, `Landing Page` -> `landing_page`, `Call Script` -> `call_script`, `Display` -> `display`.
- Risk Tier: `High` -> `high`, `Medium` -> `medium`, `Low` -> `low`.
- Status: `Not Started` -> `submitted`, `In Review` -> `in_review`, `Changes Requested` -> `changes_requested`, `Approved` -> `approved + decision approved`, `Approved w/ Changes` -> `approved + decision approved_with_edits`, `Rejected` -> `rejected + decision rejected`.
- Partners sheet Type: `Affiliate` -> `affiliate`, `Lead Gen` -> `lead_gen`, `Marketplace` -> `marketplace`, `Influencer` -> `influencer`.

## Other characteristics importer and metrics authors need

Not errors, but each one changes what a naive importer computes.

- **Comments that cross New Year** (comment dates need the year rollover): MCR-25-012 (r13), MCR-25-013 (r14), MCR-25-014 (r15), MCR-25-015 (r16), MCR-25-016 (r17), MCR-25-017 (r18).
- **Reviewer hand-offs** (initials change between rounds; Assigned Reviewer is the latest): MCR-25-001 (r2), MCR-26-003 (r22), MCR-26-032 (r51), MCR-26-041 (r60), MCR-26-049 (r69), MCR-26-063 (r83), MCR-26-067 (r87), MCR-26-074 (r94), MCR-26-078 (r98), MCR-26-082 (r102), MCR-26-084 (r104).
- **Version # = Revision Round + 1** (marketer sent v2 before the first review; Comments say so): MCR-26-003 (r22), MCR-26-026 (r45), MCR-26-044 (r63), MCR-26-052 (r72), MCR-26-064 (r84), MCR-26-082 (r102), MCR-26-083 (r103), MCR-26-106 (r127), MCR-26-115 (r136), MCR-26-126 (r147), MCR-26-140 (r161), MCR-26-145 (r166).
- **Newline-separated comment segments**: 55 multi-round cells; the rest use single spaces.
- **Five-round items**: MCR-26-032 (r51), MCR-26-081 (r101).
- **Stale Changes Requested** (last round before 2026-09-23, marketer never resubmitted): MCR-26-011 (r30), MCR-26-046 (r65), MCR-26-071 (r91), MCR-26-072 (r92), MCR-26-084 (r104).
- **Rejected**: MCR-25-002 (r3), MCR-26-001 (r20), MCR-26-037 (r56), MCR-26-052 (r72), MCR-26-066 (r86), MCR-26-134 (r155).
- **Re-review requests** (new row for an expiring or rate-changed placement; the original row still says Approved; the asset name ends `orig MCR-..`, so an importer may link them): MCR-26-080 (r100), MCR-26-081 (r101), MCR-26-084 (r104), MCR-26-086 (r106), MCR-26-088 (r108), MCR-26-089 (r109), MCR-26-093 (r113), MCR-26-111 (r132).
- **Approved, expiry already past on 2026-10-24**: MCR-25-001 (r2), MCR-25-003 (r4), MCR-25-005 (r6), MCR-25-006 (r7), MCR-25-007 (r8), MCR-25-008 (r9), MCR-25-009 (r10), MCR-25-011 (r12), MCR-25-013 (r14), MCR-25-014 (r15), MCR-25-015 (r16), MCR-25-017 (r18), MCR-26-002 (r21), MCR-26-003 (r22), MCR-26-004 (r23), MCR-26-005 (r24), MCR-26-006 (r25), MCR-26-007 (r26), MCR-26-012 (r31), MCR-26-013 (r32), MCR-26-014 (r33), MCR-26-015 (r34), MCR-26-017 (r36), MCR-26-018 (r37), MCR-26-019 (r38), MCR-26-020 (r39), MCR-26-021 (r40), MCR-26-022 (r41), MCR-26-023 (r42), MCR-26-024 (r43), MCR-26-026 (r45), MCR-26-027 (r46), MCR-26-029 (r48), MCR-26-033 (r52), MCR-26-034 (r53), MCR-26-035 (r54), MCR-26-038 (r57), MCR-26-039 (r58), MCR-26-040 (r59), MCR-26-044 (r63), MCR-26-050 (r70), MCR-26-053 (r73), MCR-26-054 (r74), MCR-26-057 (r77), MCR-26-059 (r79), MCR-26-060 (r80), MCR-26-062 (r82), MCR-26-064 (r84), MCR-26-068 (r88), MCR-26-073 (r93), MCR-26-074 (r94), MCR-26-075 (r95), MCR-26-076 (r96), MCR-26-082 (r102), MCR-26-087 (r107), MCR-26-094 (r114), MCR-26-097 (r117), MCR-26-099 (r119), MCR-26-100 (r120), MCR-26-101 (r121), MCR-26-102 (r123), MCR-26-103 (r124), MCR-26-106 (r127), MCR-26-107 (r128), MCR-26-109 (r130), MCR-26-110 (r131). Legacy items are excluded from the expiry sweep (spec 4.2.7), so these import as approved with a past `expires_at`.
- **Rate sheet change 6/1/26**: the PL APR floor moved from 8.99% to 9.49%. Comments before 6/1 quote 8.99%; some later ones flag the old floor.
- **Reg B rewrite 7/21/26**: fair-lending comments after that date cite the rewritten 1002.4(b).
- **Holiday freeze 12/22/25-1/2/26**: no comment segment is dated inside it (the merged note row says so).
- Partner rows always postdate that partner's agreement date on the Partners sheet.
