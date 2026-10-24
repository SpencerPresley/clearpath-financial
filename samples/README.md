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
- Submitted 2025-09-02 to 2026-08-12; the tracker was last updated 2026-08-14.
- Open (submitted or in review) on 2026-08-14: 20; unassigned: 8.

| Canonical status | Items |
|---|---|
| approved (decision: approved) | 125 |
| approved (decision: approved_with_edits) | 14 |
| changes_requested | 10 |
| in_review | 12 |
| rejected (decision: rejected) | 9 |
| submitted | 8 |

## Intended messiness (the oracle)

Each kind lists every affected cell. `rN` is the Excel row number. Values in backticks are exact, including spaces; `(empty)` is an empty cell. 'Importer should' is the required behaviour.

### Status spelling variants

Importer should: Map case- and whitespace-insensitively through the status table below. A blank Status is approved (decision approved, with a warning) when the Approval cell is filled, otherwise submitted. Values outside the table are a preview problem, not a guess.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-013 | r14 | Status | `"Needs changes"` | changes_requested |
| MCR-25-041 | r42 | Status | `"approved "` | approved (decision: approved) |
| MCR-26-002 | r45 | Status | `"Needs changes"` | changes_requested |
| MCR-26-011 | r54 | Status | `"Approved - minor edits"` | approved (decision: approved_with_edits) |
| MCR-26-023 | r66 | Status | `"Approved - minor edits"` | approved (decision: approved_with_edits) |
| MCR-26-039 | r83 | Status | `"approved "` | approved (decision: approved) |
| MCR-26-045 | r89 | Status | `"Approved w/ changes"` | approved (decision: approved_with_edits) |
| MCR-26-051 | r95 | Status | `"Needs changes"` | changes_requested |
| MCR-26-056 | r100 | Status | `"Changes Req."` | changes_requested |
| MCR-26-060 | r104 | Status | `"Approved w/ changes"` | approved (decision: approved_with_edits) |
| MCR-26-073 | r117 | Status | `"Approved - minor edits"` | approved (decision: approved_with_edits) |
| MCR-26-084 | r129 | Status | `"approved "` | approved (decision: approved) |
| MCR-26-090 | r135 | Status | `"approved "` | approved (decision: approved) |
| MCR-26-107 | r152 | Status | `"Approved - minor edits"` | approved (decision: approved_with_edits) |
| MCR-26-108 | r153 | Status | `(empty)` | approved (decision: approved) - inferred from the filled Approval cell; emit a warning |
| MCR-26-109 | r154 | Status | `"in review"` | in_review |
| MCR-26-111 | r156 | Status | `"in review"` | in_review |
| MCR-26-117 | r162 | Status | `"Changes Req."` | changes_requested |
| MCR-26-118 | r163 | Status | `"Approved w/ changes"` | approved (decision: approved_with_edits) |
| MCR-26-120 | r165 | Status | `"Changes Req."` | changes_requested |
| MCR-26-126 | r171 | Status | `"Pending"` | submitted |
| MCR-26-127 | r172 | Status | `(empty)` | submitted |
| MCR-26-128 | r173 | Status | `"in review"` | in_review |
| MCR-26-129 | r174 | Status | `(empty)` | submitted |
| MCR-26-131 | r176 | Status | `"Pending"` | submitted |
| MCR-26-132 | r177 | Status | `"Pending"` | submitted |
| MCR-26-136 | r181 | Status | `(empty)` | submitted |

### Product spelling variants

Importer should: Strip, then map case-insensitively: PL / Personal Loan / personal loans -> personal_loan, CC / Credit Card -> credit_card, MTG / Mortgage Prequal -> mortgage_prequal.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-002 | r3 | Product | `"PL"` | personal_loan |
| MCR-25-004 | r5 | Product | `"PL"` | personal_loan |
| MCR-25-008 | r9 | Product | `"personal loans"` | personal_loan |
| MCR-25-013 | r14 | Product | `"PL"` | personal_loan |
| MCR-25-014 | r15 | Product | `"PL"` | personal_loan |
| MCR-25-018 | r19 | Product | `"PL"` | personal_loan |
| MCR-25-032 | r33 | Product | `"CC"` | credit_card |
| MCR-25-040 | r41 | Product | `"CC"` | credit_card |
| MCR-26-003 | r46 | Product | `"CC"` | credit_card |
| MCR-26-009 | r52 | Product | `"personal loans"` | personal_loan |
| MCR-26-018 | r61 | Product | `"CC"` | credit_card |
| MCR-26-020 | r63 | Product | `"personal loans"` | personal_loan |
| MCR-26-029 | r73 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-032 | r76 | Product | `"CC"` | credit_card |
| MCR-26-036 | r80 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-038 | r82 | Product | `"PL"` | personal_loan |
| MCR-26-040 | r84 | Product | `"PL"` | personal_loan |
| MCR-26-052 | r96 | Product | `"PL"` | personal_loan |
| MCR-26-054 | r98 | Product | `"PL"` | personal_loan |
| MCR-26-055 | r99 | Product | `"CC"` | credit_card |
| MCR-26-056 | r100 | Product | `"CC"` | credit_card |
| MCR-26-057 | r101 | Product | `"CC"` | credit_card |
| MCR-26-065 | r109 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-072 | r116 | Product | `"PL"` | personal_loan |
| MCR-26-078 | r123 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-083 | r128 | Product | `"PL"` | personal_loan |
| MCR-26-084 | r129 | Product | `"PL"` | personal_loan |
| MCR-26-088 | r133 | Product | `"PL"` | personal_loan |
| MCR-26-090 | r135 | Product | `"CC"` | credit_card |
| MCR-26-105 | r150 | Product | `"CC"` | credit_card |
| MCR-26-114 | r159 | Product | `"personal loans"` | personal_loan |
| MCR-26-117 | r162 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-120 | r165 | Product | `"MTG"` | mortgage_prequal |
| MCR-26-125 | r170 | Product | `"PL"` | personal_loan |

### Date Submitted stored as text

Importer should: Accept real dates, `M/D/YY` (US order, 20YY), ISO `YYYY-MM-DD`, and `Mon D` with the year taken from the Request ID prefix. Report each coerced cell as an info-level note.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-002 | r3 | Date Submitted | `"Sep 8"` | 2025-09-08 (year from the MCR-YY- prefix) |
| MCR-25-004 | r5 | Date Submitted | `"9/12/25"` | 2025-09-12 |
| MCR-25-008 | r9 | Date Submitted | `"2025-09-24"` | 2025-09-24 |
| MCR-25-019 | r20 | Date Submitted | `"Oct 27"` | 2025-10-27 (year from the MCR-YY- prefix) |
| MCR-25-029 | r30 | Date Submitted | `"11/21/25"` | 2025-11-21 |
| MCR-26-015 | r58 | Date Submitted | `"2/4/26"` | 2026-02-04 |
| MCR-26-017 | r60 | Date Submitted | `"2/4/26"` | 2026-02-04 |
| MCR-26-018 | r61 | Date Submitted | `"2026-02-05"` | 2026-02-05 |
| MCR-26-019 | r62 | Date Submitted | `"2026-02-06"` | 2026-02-06 |
| MCR-26-066 | r110 | Date Submitted | `"5/5/26"` | 2026-05-05 |
| MCR-26-094 | r139 | Date Submitted | `"Jun 24"` | 2026-06-24 (year from the MCR-YY- prefix) |
| MCR-26-095 | r140 | Date Submitted | `"2026-06-26"` | 2026-06-26 |
| MCR-26-104 | r149 | Date Submitted | `"Jul 14"` | 2026-07-14 (year from the MCR-YY- prefix) |
| MCR-26-112 | r157 | Date Submitted | `"7/22/26"` | 2026-07-22 |
| MCR-26-113 | r158 | Date Submitted | `"2026-07-23"` | 2026-07-23 |

### Expiration stored as text

Importer should: Same parser as Date Submitted (`M/D/YY` text).

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-010 | r53 | Approval Expiration / Re-review Date | `"2/19/26"` | 2026-02-19 |
| MCR-26-048 | r92 | Approval Expiration / Re-review Date | `"11/22/26"` | 2026-11-22 |
| MCR-26-065 | r109 | Approval Expiration / Re-review Date | `"12/17/26"` | 2026-12-17 |

### Approval cell with approver only (no date)

Importer should: Approver resolved from `F. Last` to the reviewer; approval date taken from the final comment segment (and flagged as derived).

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-004 | r5 | Approval Date & Approver | `"S. Ortega"` | approver Samuel Ortega; date 2025-09-26 from the last R-segment in Comments |
| MCR-25-032 | r33 | Approval Date & Approver | `"S. Ortega"` | approver Samuel Ortega; date 2025-12-09 from the last R-segment in Comments |
| MCR-26-006 | r49 | Approval Date & Approver | `"D. Kim"` | approver Dana Kim; date 2026-01-23 from the last R-segment in Comments |
| MCR-26-026 | r70 | Approval Date & Approver | `"S. Ortega"` | approver Samuel Ortega; date 2026-03-03 from the last R-segment in Comments |
| MCR-26-040 | r84 | Approval Date & Approver | `"L. Brandt"` | approver Leah Brandt; date 2026-04-13 from the last R-segment in Comments |
| MCR-26-100 | r145 | Approval Date & Approver | `"S. Ortega"` | approver Samuel Ortega; date 2026-07-27 from the last R-segment in Comments |

### Approved row with blank expiration

Importer should: Store `expires_at` null and report it. Do not invent a date (the generator's policy default is shown only so tests can tell the rows apart).

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-008 | r9 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2025-11-08) |
| MCR-25-011 | r12 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2026-04-09) |
| MCR-25-024 | r25 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2025-12-27) |
| MCR-26-024 | r67 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2026-03-25) |
| MCR-26-081 | r126 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2026-12-23) |
| MCR-26-121 | r166 | Approval Expiration / Re-review Date | `(empty)` | expires_at null + 'missing expiry' warning (policy default would be 2027-02-14) |

### Exact duplicate row

Importer should: Rows identical in every cell are one item.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-021 | r64, r68 | (whole row) | `every cell identical, including hyperlinks` | import one item; report the second row as a duplicate and skip it |

### Request ID reused for a different asset

Importer should: Same Request ID, different Asset Name / Date Submitted: two items. The discriminator is (Asset Name, Date Submitted); identical values mean duplicate, different mean reuse.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-26-077 | r121, r122 | Request ID | `"MCR-26-077"` | two items: r121 'CC Double Points search ads' (submitted 2026-05-26) and r122 'HomeBound Leads - MTG Bay Area Buyers call script' (submitted 2026-05-27). Import both; the later row gets a disambiguated legacy_ref (e.g. MCR-26-077-b) and an admin warning |

### Leading / trailing whitespace

Importer should: Strip every string cell before matching or storing.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-019 | r20 | Submitter / BU | `"Jordan Whitfield / Partnerships & Affiliates  "` | "Jordan Whitfield / Partnerships & Affiliates" after strip() |
| MCR-25-024 | r25 | Channel | `"Email "` | "Email" after strip() |
| MCR-26-015 | r58 | Affiliate / Partner | `" Money with Maya "` | "Money with Maya" after strip() |
| MCR-26-020 | r63 | Request ID | `"MCR-26-020 "` | "MCR-26-020" after strip() |
| MCR-26-023 | r66 | Product | `" Credit Card"` | "Credit Card" after strip() |
| MCR-26-036 | r80 | Affiliate / Partner | `" HomeBound Leads "` | "HomeBound Leads" after strip() |
| MCR-26-037 | r81 | Assigned Reviewer | `"Nikhil Rao "` | "Nikhil Rao" after strip() |
| MCR-26-046 | r90 | Assigned Reviewer | `"Dana Kim "` | "Dana Kim" after strip() |
| MCR-26-113 | r158 | Submitter / BU | `"Jordan Whitfield / Partnerships & Affiliates  "` | "Jordan Whitfield / Partnerships & Affiliates" after strip() |

### Partner typed differently from the Partners sheet

Importer should: Match partners by a normalized key (casefold, drop spaces and punctuation) against the Partners sheet; the bare `CardPerks` resolves to `CardPerks Weekly` because it is a unique prefix. Report each fuzzy match.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-019 | r20 | Affiliate / Partner | `"Lend Compare"` | partner 'LendCompare' |
| MCR-26-028 | r72 | Affiliate / Partner | `"Leadstream Direct"` | partner 'LeadStream Direct' |
| MCR-26-055 | r99 | Affiliate / Partner | `"Lend Compare"` | partner 'LendCompare' |
| MCR-26-105 | r150 | Affiliate / Partner | `"CardPerks"` | partner 'CardPerks Weekly' |

### Trigger Terms Y/N variants

Importer should: `Y`/`yes` -> true, `N` -> false, blank or `?` -> null with a warning. Do not infer from comments.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| MCR-25-014 | r15 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was N |
| MCR-25-015 | r16 | Trigger Terms Present (Y/N) | `"?"` | null (unknown) + warning; generator truth was Y |
| MCR-25-036 | r37 | Trigger Terms Present (Y/N) | `"?"` | null (unknown) + warning; generator truth was Y |
| MCR-26-006 | r49 | Trigger Terms Present (Y/N) | `"?"` | null (unknown) + warning; generator truth was N |
| MCR-26-018 | r61 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-040 | r84 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-082 | r127 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was Y |
| MCR-26-084 | r129 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was Y |
| MCR-26-088 | r133 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-111 | r156 | Trigger Terms Present (Y/N) | `"yes"` | true |
| MCR-26-120 | r165 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was Y |
| MCR-26-130 | r175 | Trigger Terms Present (Y/N) | `(empty)` | null (unknown) + warning; generator truth was N |
| MCR-26-135 | r180 | Trigger Terms Present (Y/N) | `"yes"` | true |

### Merged note row inside the data

Importer should: Skip rows whose stripped column A does not match the Request ID pattern; report them.

| Request ID | Row(s) | Column | Raw | Expected |
|---|---|---|---|---|
| (none) | r43 | A43:Q43 merged | `"NOTE (R. Okafor 1/5/26): holiday review freeze 12/22 - 1/2, ..."` | skip: column A does not match the Request ID pattern; report it as a skipped non-data row |

### Links: hyperlink objects vs text

Importer should: read `cell.hyperlink.target` when a hyperlink exists (the display text may be a label such as `LendCompare listing`), otherwise extract URLs from the text with a regex. Hyperlinked cells:

- **Asset Name / File Link**: 96 hyperlinked cells: MCR-25-003 (r4), MCR-25-006 (r7), MCR-25-010 (r11), MCR-25-011 (r12), MCR-25-014 (r15), MCR-25-021 (r22), MCR-25-030 (r31), MCR-25-033 (r34), MCR-25-036 (r37), MCR-25-037 (r38), MCR-25-039 (r40), MCR-26-003 (r46), MCR-26-014 (r57), MCR-26-015 (r58), MCR-26-017 (r60), MCR-26-018 (r61), MCR-26-019 (r62), MCR-26-021 (r64), MCR-26-023 (r66), MCR-26-021 (r68), MCR-26-025 (r69), MCR-26-026 (r70), MCR-26-029 (r73), MCR-26-031 (r75), MCR-26-032 (r76), MCR-26-034 (r78), MCR-26-037 (r81), MCR-26-038 (r82), MCR-26-039 (r83), MCR-26-040 (r84), MCR-26-043 (r87), MCR-26-044 (r88), MCR-26-045 (r89), MCR-26-048 (r92), MCR-26-050 (r94), MCR-26-051 (r95), MCR-26-052 (r96), MCR-26-053 (r97), MCR-26-055 (r99), MCR-26-056 (r100), MCR-26-057 (r101), MCR-26-058 (r102), MCR-26-059 (r103), MCR-26-061 (r105), MCR-26-062 (r106), MCR-26-063 (r107), MCR-26-064 (r108), MCR-26-065 (r109), MCR-26-067 (r111), MCR-26-068 (r112), MCR-26-070 (r114), MCR-26-071 (r115), MCR-26-073 (r117), MCR-26-074 (r118), MCR-26-077 (r121), MCR-26-077 (r122), MCR-26-080 (r125), MCR-26-082 (r127), MCR-26-084 (r129), MCR-26-085 (r130), MCR-26-086 (r131), MCR-26-087 (r132), MCR-26-088 (r133), MCR-26-089 (r134), MCR-26-090 (r135), MCR-26-092 (r137), MCR-26-093 (r138), MCR-26-094 (r139), MCR-26-095 (r140), MCR-26-097 (r142), MCR-26-098 (r143), MCR-26-099 (r144), MCR-26-100 (r145), MCR-26-103 (r148), MCR-26-104 (r149), MCR-26-105 (r150), MCR-26-106 (r151), MCR-26-109 (r154), MCR-26-110 (r155), MCR-26-111 (r156), MCR-26-112 (r157), MCR-26-113 (r158), MCR-26-114 (r159), MCR-26-117 (r162), MCR-26-118 (r163), MCR-26-120 (r165), MCR-26-121 (r166), MCR-26-123 (r168), MCR-26-125 (r170), MCR-26-126 (r171), MCR-26-127 (r172), MCR-26-128 (r173), MCR-26-130 (r175), MCR-26-132 (r177), MCR-26-135 (r180), MCR-26-136 (r181).
  - Text containing a URL, no hyperlink object (58): MCR-25-001 (r2), MCR-25-002 (r3), MCR-25-004 (r5), MCR-25-005 (r6), MCR-25-007 (r8), MCR-25-008 (r9), MCR-25-012 (r13), MCR-25-013 (r14), MCR-25-015 (r16), MCR-25-017 (r18), MCR-25-018 (r19), MCR-25-020 (r21), MCR-25-022 (r23), MCR-25-024 (r25), MCR-25-025 (r26), MCR-25-026 (r27), MCR-25-028 (r29), MCR-25-031 (r32), MCR-25-034 (r35), MCR-25-038 (r39), MCR-25-040 (r41), MCR-25-041 (r42), MCR-26-002 (r45), MCR-26-004 (r47), MCR-26-005 (r48), MCR-26-007 (r50), MCR-26-009 (r52), MCR-26-010 (r53), MCR-26-016 (r59), MCR-26-020 (r63), MCR-26-022 (r65), MCR-26-024 (r67), MCR-26-027 (r71), MCR-26-030 (r74), MCR-26-033 (r77), MCR-26-035 (r79), MCR-26-041 (r85), MCR-26-046 (r90), MCR-26-047 (r91), MCR-26-060 (r104), MCR-26-066 (r110), MCR-26-072 (r116), MCR-26-075 (r119), MCR-26-076 (r120), MCR-26-078 (r123), MCR-26-079 (r124), MCR-26-081 (r126), MCR-26-091 (r136), MCR-26-096 (r141), MCR-26-102 (r147), MCR-26-108 (r153), MCR-26-115 (r160), MCR-26-116 (r161), MCR-26-119 (r164), MCR-26-122 (r167), MCR-26-124 (r169), MCR-26-133 (r178), MCR-26-134 (r179).
  - Asset name only, no link at all (25): MCR-25-009 (r10), MCR-25-016 (r17), MCR-25-019 (r20), MCR-25-023 (r24), MCR-25-027 (r28), MCR-25-029 (r30), MCR-25-032 (r33), MCR-25-035 (r36), MCR-26-001 (r44), MCR-26-006 (r49), MCR-26-008 (r51), MCR-26-011 (r54), MCR-26-012 (r55), MCR-26-013 (r56), MCR-26-028 (r72), MCR-26-036 (r80), MCR-26-042 (r86), MCR-26-049 (r93), MCR-26-054 (r98), MCR-26-069 (r113), MCR-26-083 (r128), MCR-26-101 (r146), MCR-26-107 (r152), MCR-26-129 (r174), MCR-26-131 (r176).
- **Live URL / Placement & Screenshot Link**: 7 hyperlinked cells: MCR-26-046 (r90), MCR-26-058 (r102), MCR-26-067 (r111), MCR-26-073 (r117), MCR-26-074 (r118), MCR-26-089 (r134), MCR-26-098 (r143).
  - Display text differs from the target (friendly label): MCR-26-074 (r118).
  - Text containing a URL, no hyperlink object (87): MCR-25-001 (r2), MCR-25-002 (r3), MCR-25-003 (r4), MCR-25-004 (r5), MCR-25-005 (r6), MCR-25-007 (r8), MCR-25-008 (r9), MCR-25-011 (r12), MCR-25-012 (r13), MCR-25-014 (r15), MCR-25-015 (r16), MCR-25-016 (r17), MCR-25-017 (r18), MCR-25-018 (r19), MCR-25-019 (r20), MCR-25-020 (r21), MCR-25-022 (r23), MCR-25-023 (r24), MCR-25-024 (r25), MCR-25-025 (r26), MCR-25-026 (r27), MCR-25-028 (r29), MCR-25-030 (r31), MCR-25-032 (r33), MCR-25-036 (r37), MCR-25-037 (r38), MCR-25-038 (r39), MCR-25-039 (r40), MCR-25-041 (r42), MCR-26-003 (r46), MCR-26-006 (r49), MCR-26-007 (r50), MCR-26-010 (r53), MCR-26-011 (r54), MCR-26-012 (r55), MCR-26-013 (r56), MCR-26-015 (r58), MCR-26-016 (r59), MCR-26-017 (r60), MCR-26-019 (r62), MCR-26-022 (r65), MCR-26-023 (r66), MCR-26-024 (r67), MCR-26-025 (r69), MCR-26-027 (r71), MCR-26-028 (r72), MCR-26-029 (r73), MCR-26-030 (r74), MCR-26-033 (r77), MCR-26-034 (r78), MCR-26-035 (r79), MCR-26-036 (r80), MCR-26-039 (r83), MCR-26-040 (r84), MCR-26-041 (r85), MCR-26-042 (r86), MCR-26-044 (r88), MCR-26-045 (r89), MCR-26-047 (r91), MCR-26-048 (r92), MCR-26-050 (r94), MCR-26-052 (r96), MCR-26-053 (r97), MCR-26-061 (r105), MCR-26-062 (r106), MCR-26-063 (r107), MCR-26-066 (r110), MCR-26-072 (r116), MCR-26-075 (r119), MCR-26-076 (r120), MCR-26-078 (r123), MCR-26-079 (r124), MCR-26-080 (r125), MCR-26-082 (r127), MCR-26-084 (r129), MCR-26-085 (r130), MCR-26-086 (r131), MCR-26-088 (r133), MCR-26-090 (r135), MCR-26-091 (r136), MCR-26-093 (r138), MCR-26-094 (r139), MCR-26-100 (r145), MCR-26-101 (r146), MCR-26-107 (r152), MCR-26-108 (r153), MCR-26-118 (r163).

## Every raw value, mapped

Exhaustive over all data rows (the duplicate row included). For Trigger Terms the Canonical column is the generator's truth; the importer must still store blank and `?` as null.

### Status values

| Raw cell | Canonical | Rows | Where (off-list values only) |
|---|---|---|---|
| `"Approved - minor edits"` | approved (decision: approved_with_edits) | 4 | MCR-26-011 (r54), MCR-26-023 (r66), MCR-26-073 (r117), MCR-26-107 (r152) |
| `"Approved w/ Changes"` | approved (decision: approved_with_edits) | 7 |  |
| `"Approved w/ changes"` | approved (decision: approved_with_edits) | 3 | MCR-26-045 (r89), MCR-26-060 (r104), MCR-26-118 (r163) |
| `"Approved"` | approved (decision: approved) | 121 |  |
| `"Changes Req."` | changes_requested | 3 | MCR-26-056 (r100), MCR-26-117 (r162), MCR-26-120 (r165) |
| `"Changes Requested"` | changes_requested | 4 |  |
| `"In Review"` | in_review | 9 |  |
| `"Needs changes"` | changes_requested | 3 | MCR-25-013 (r14), MCR-26-002 (r45), MCR-26-051 (r95) |
| `"Not Started"` | submitted | 2 |  |
| `"Pending"` | submitted | 3 | MCR-26-126 (r171), MCR-26-131 (r176), MCR-26-132 (r177) |
| `"Rejected"` | rejected (decision: rejected) | 9 |  |
| `"approved "` | approved (decision: approved) | 4 | MCR-25-041 (r42), MCR-26-039 (r83), MCR-26-084 (r129), MCR-26-090 (r135) |
| `"in review"` | in_review | 3 | MCR-26-109 (r154), MCR-26-111 (r156), MCR-26-128 (r173) |
| `(empty)` | approved (decision: approved) | 1 | MCR-26-108 (r153) |
| `(empty)` | submitted | 3 | MCR-26-127 (r172), MCR-26-129 (r174), MCR-26-136 (r181) |

### Product values

| Raw cell | Canonical | Rows | Where (off-list values only) |
|---|---|---|---|
| `" Credit Card"` | credit_card | 1 | MCR-26-023 (r66) |
| `"CC"` | credit_card | 10 | MCR-25-032 (r33), MCR-25-040 (r41), MCR-26-003 (r46), MCR-26-018 (r61), MCR-26-032 (r76), MCR-26-055 (r99), MCR-26-056 (r100), MCR-26-057 (r101), MCR-26-090 (r135), MCR-26-105 (r150) |
| `"Credit Card"` | credit_card | 46 |  |
| `"MTG"` | mortgage_prequal | 6 | MCR-26-029 (r73), MCR-26-036 (r80), MCR-26-065 (r109), MCR-26-078 (r123), MCR-26-117 (r162), MCR-26-120 (r165) |
| `"Mortgage Prequal"` | mortgage_prequal | 32 |  |
| `"PL"` | personal_loan | 14 | MCR-25-002 (r3), MCR-25-004 (r5), MCR-25-013 (r14), MCR-25-014 (r15), MCR-25-018 (r19), MCR-26-038 (r82), MCR-26-040 (r84), MCR-26-052 (r96), MCR-26-054 (r98), MCR-26-072 (r116), MCR-26-083 (r128), MCR-26-084 (r129), MCR-26-088 (r133), MCR-26-125 (r170) |
| `"Personal Loan"` | personal_loan | 66 |  |
| `"personal loans"` | personal_loan | 4 | MCR-25-008 (r9), MCR-26-009 (r52), MCR-26-020 (r63), MCR-26-114 (r159) |

### Trigger Terms values

| Raw cell | Canonical | Rows | Where (off-list values only) |
|---|---|---|---|
| `"?"` | N | 1 | MCR-26-006 (r49) |
| `"?"` | Y | 2 | MCR-25-015 (r16), MCR-25-036 (r37) |
| `"N"` | N | 104 |  |
| `"Y"` | Y | 62 |  |
| `"yes"` | Y | 5 | MCR-26-018 (r61), MCR-26-040 (r84), MCR-26-088 (r133), MCR-26-111 (r156), MCR-26-135 (r180) |
| `(empty)` | N | 2 | MCR-25-014 (r15), MCR-26-130 (r175) |
| `(empty)` | Y | 3 | MCR-26-082 (r127), MCR-26-084 (r129), MCR-26-120 (r165) |

### Partner values

| Raw cell | Canonical | Rows | Where (off-list values only) |
|---|---|---|---|
| `" HomeBound Leads "` | HomeBound Leads | 1 | MCR-26-036 (r80) |
| `" Money with Maya "` | Money with Maya | 1 | MCR-26-015 (r58) |
| `"CardPerks Weekly"` | CardPerks Weekly | 6 |  |
| `"CardPerks"` | CardPerks Weekly | 1 | MCR-26-105 (r150) |
| `"FinMatch"` | FinMatch | 4 |  |
| `"Golden State Saver"` | Golden State Saver | 3 |  |
| `"HomeBound Leads"` | HomeBound Leads | 3 |  |
| `"LeadStream Direct"` | LeadStream Direct | 2 |  |
| `"Leadstream Direct"` | LeadStream Direct | 1 | MCR-26-028 (r72) |
| `"Lend Compare"` | LendCompare | 2 | MCR-25-019 (r20), MCR-26-055 (r99) |
| `"LendCompare"` | LendCompare | 3 |  |
| `"Money with Maya"` | Money with Maya | 2 |  |
| `"RateRadar"` | RateRadar | 7 |  |
| `(empty)` | (none) | 143 |  |

### Clean labels to app vocabulary (`backend/core/domain.py`)

- Product: `Personal Loan` -> `personal_loan`, `Credit Card` -> `credit_card`, `Mortgage Prequal` -> `mortgage_prequal`.
- Channel: `Email` -> `email`, `Paid Social` -> `paid_social`, `Paid Search` -> `paid_search`, `Direct Mail` -> `direct_mail`, `Affiliate Page` -> `affiliate_page`, `SMS` -> `sms`, `Landing Page` -> `landing_page`, `Call Script` -> `call_script`, `Display` -> `display`.
- Risk Tier: `High` -> `high`, `Medium` -> `medium`, `Low` -> `low`.
- Status: `Not Started` -> `submitted`, `In Review` -> `in_review`, `Changes Requested` -> `changes_requested`, `Approved` -> `approved + decision approved`, `Approved w/ Changes` -> `approved + decision approved_with_edits`, `Rejected` -> `rejected + decision rejected`.
- Partners sheet Type: `Affiliate` -> `affiliate`, `Lead Gen` -> `lead_gen`, `Marketplace` -> `marketplace`, `Influencer` -> `influencer`.

## Other characteristics importer and metrics authors need

Not errors, but each one changes what a naive importer computes.

- **Comments that cross New Year** (comment dates need the year rollover): MCR-25-033 (r34), MCR-25-036 (r37), MCR-25-038 (r39), MCR-25-039 (r40), MCR-25-040 (r41), MCR-25-041 (r42).
- **Reviewer hand-offs** (initials change between rounds; Assigned Reviewer is the latest): MCR-25-013 (r14), MCR-26-003 (r46), MCR-26-005 (r48), MCR-26-026 (r70), MCR-26-068 (r112), MCR-26-069 (r113), MCR-26-076 (r120), MCR-26-088 (r133).
- **Version # = Revision Round + 1** (marketer sent v2 before the first review; Comments say so): MCR-25-004 (r5), MCR-25-011 (r12), MCR-25-017 (r18), MCR-25-024 (r25), MCR-26-002 (r45), MCR-26-008 (r51), MCR-26-038 (r82), MCR-26-077 (r121), MCR-26-110 (r155), MCR-26-129 (r174).
- **Newline-separated comment segments**: 50 multi-round cells; the rest use single spaces.
- **Five-round items**: MCR-26-021 (r64), MCR-26-069 (r113), MCR-26-080 (r125), MCR-26-092 (r137).
- **Stale Changes Requested** (last round before 2026-07-15, marketer never resubmitted): MCR-25-013 (r14), MCR-26-002 (r45), MCR-26-051 (r95), MCR-26-056 (r100), MCR-26-077 (r122).
- **Rejected**: MCR-25-006 (r7), MCR-25-009 (r10), MCR-25-027 (r28), MCR-25-040 (r41), MCR-26-043 (r87), MCR-26-055 (r99), MCR-26-064 (r108), MCR-26-070 (r114), MCR-26-077 (r121).
- **Re-review requests** (new row for an expiring or rate-changed placement; the original row still says Approved; the asset name ends `orig MCR-..`, so an importer may link them): MCR-26-064 (r108), MCR-26-067 (r111), MCR-26-074 (r118), MCR-26-082 (r127), MCR-26-083 (r128), MCR-26-085 (r130), MCR-26-088 (r133), MCR-26-089 (r134), MCR-26-092 (r137), MCR-26-124 (r169).
- **Approved, expiry already past on 2026-08-15**: MCR-25-001 (r2), MCR-25-003 (r4), MCR-25-004 (r5), MCR-25-005 (r6), MCR-25-007 (r8), MCR-25-010 (r11), MCR-25-012 (r13), MCR-25-014 (r15), MCR-25-015 (r16), MCR-25-016 (r17), MCR-25-017 (r18), MCR-25-018 (r19), MCR-25-019 (r20), MCR-25-021 (r22), MCR-25-022 (r23), MCR-25-023 (r24), MCR-25-025 (r26), MCR-25-026 (r27), MCR-25-031 (r32), MCR-25-032 (r33), MCR-25-033 (r34), MCR-25-036 (r37), MCR-25-037 (r38), MCR-25-038 (r39), MCR-25-039 (r40), MCR-25-041 (r42), MCR-26-001 (r44), MCR-26-004 (r47), MCR-26-005 (r48), MCR-26-006 (r49), MCR-26-007 (r50), MCR-26-009 (r52), MCR-26-010 (r53), MCR-26-011 (r54), MCR-26-012 (r55), MCR-26-014 (r57), MCR-26-016 (r59), MCR-26-017 (r60), MCR-26-023 (r66), MCR-26-027 (r71), MCR-26-028 (r72), MCR-26-029 (r73), MCR-26-030 (r74), MCR-26-031 (r75), MCR-26-032 (r76), MCR-26-034 (r78), MCR-26-038 (r82), MCR-26-039 (r83), MCR-26-041 (r85), MCR-26-044 (r88), MCR-26-053 (r97), MCR-26-060 (r104), MCR-26-063 (r107), MCR-26-076 (r120), MCR-26-086 (r131), MCR-26-087 (r132), MCR-26-090 (r135), MCR-26-097 (r142). Legacy items are excluded from the expiry sweep (spec 4.2.7), so these import as approved with a past `expires_at`.
- **Rate sheet change 6/1/26**: the PL APR floor moved from 8.99% to 9.49%. Comments before 6/1 quote 8.99%; some later ones flag the old floor.
- **Reg B rewrite 7/21/26**: fair-lending comments after that date cite the rewritten 1002.4(b).
- **Holiday freeze 12/22/25-1/2/26**: no comment segment is dated inside it (the merged note row says so).
- Partner rows always postdate that partner's agreement date on the Partners sheet.
