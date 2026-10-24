"""The importer against samples/README.md. Each "Intended messiness" table and each "Every raw value, mapped"
table is read from the README itself (tests/oracle.py) and checked row by row."""

import re
from collections import Counter
from datetime import UTC, date, datetime

import pytest

from core.domain import Channel, DecisionOutcome, ItemStatus, Product
from imports.domain import ImportProblemKind, ImportTargetField, ImportValueField, ProblemSeverity, RowAction
from imports.mapping import PRODUCT_MAP, guess_column_mapping, guess_target, value_key
from imports.normalize import (
    ImportMapping,
    NormalizedImport,
    ParsedRow,
    PartnerDirectory,
    PartnerMatch,
    StatusOverride,
    ValueOverride,
    normalize,
    parse_date,
    resolve_person,
    split_asset,
)
from imports.tests import oracle
from imports.workbook import RawCell, RawWorkbook

pytestmark = pytest.mark.skipif(not oracle.README.exists(), reason="samples/ is outside the backend image")

K = ImportProblemKind
S = ProblemSeverity
T = ImportTargetField


def _directory(wb: RawWorkbook, existing: tuple[str, ...] = ()) -> PartnerDirectory:
    return PartnerDirectory.build(existing=existing, sheet=[p.name for p in wb.partners])


def _run(wb: RawWorkbook, mapping: ImportMapping | None = None, existing_refs: frozenset[str] = frozenset()):
    mapping = mapping or ImportMapping(columns=guess_column_mapping(wb.tracker.headers))
    return normalize(wb, mapping, _directory(wb), existing_refs)


@pytest.fixture
def result(sample_workbook: RawWorkbook) -> NormalizedImport:
    return _run(sample_workbook)


def _by_row(result: NormalizedImport) -> dict[int, ParsedRow]:
    return {r.row_number: r for r in result.rows}


def _kinds(row: ParsedRow) -> set[tuple[ImportProblemKind, ProblemSeverity]]:
    return {(p.kind, p.severity) for p in row.problems}


def _with_cell(wb: RawWorkbook, row_number: int, header: str, cell: RawCell) -> RawWorkbook:
    col = wb.tracker.headers.index(header)
    rows = tuple(
        r.model_copy(update={"cells": tuple(cell if i == col else c for i, c in enumerate(r.cells))})
        if r.row_number == row_number
        else r
        for r in wb.tracker.rows
    )
    return wb.model_copy(update={"tracker": wb.tracker.model_copy(update={"rows": rows})})


def _ids(r: oracle.MessRow) -> str:
    return f"{r.request_id}-r{r.rows[0]}-{r.column}"


# --- column mapping --------------------------------------------------------------------------------------------


def test_guesses_every_sample_column(sample_workbook: RawWorkbook) -> None:
    assert guess_column_mapping(sample_workbook.tracker.headers) == {
        "Request ID": T.LEGACY_REF,
        "Date Submitted": T.SUBMITTED_ON,
        "Submitter / BU": T.SUBMITTER,
        "Product": T.PRODUCT,
        "Channel": T.CHANNEL,
        "Asset Name / File Link": T.TITLE,
        "Affiliate / Partner": T.PARTNER,
        "Risk Tier": T.RISK_TIER,
        "Trigger Terms Present (Y/N)": T.TRIGGER_TERMS,
        "Assigned Reviewer": T.REVIEWER,
        "Version #": T.VERSION_NUMBER,
        "Revision Round": T.ROUNDS,
        "Status": T.STATUS,
        "Reviewer Comments / Required Changes": T.COMMENTS,
        "Approval Date & Approver": T.APPROVAL,
        "Approval Expiration / Re-review Date": T.EXPIRES_ON,
        "Live URL / Placement & Screenshot Link": T.PLACEMENT,
    }


def test_second_column_guessing_the_same_target_is_ignored() -> None:
    assert guess_column_mapping(["Status", "Status (old)"]) == {"Status": T.STATUS, "Status (old)": T.IGNORE}


# --- expected import totals ------------------------------------------------------------------------------------


def test_expected_import_totals(result: NormalizedImport) -> None:
    created = [r for r in result.rows if r.action is RowAction.CREATE]

    assert result.counts.rows_total == 180
    assert result.counts.not_data == 1
    assert result.counts.duplicates == 1
    assert result.counts.blocked == 0
    assert result.counts.ready == 178
    assert len({r.source_ref for r in created}) == 177
    assert len({r.legacy_ref for r in created}) == 178
    assert min(r.submitted_on for r in created if r.submitted_on) == date(2025, 9, 2)
    assert max(r.submitted_on for r in created if r.submitted_on) == date(2026, 8, 12)
    assert result.unmapped == ()
    assert not [p for p in result.all_problems if p.severity is S.ERROR]


def test_expected_status_totals(result: NormalizedImport) -> None:
    created = [r for r in result.rows if r.action is RowAction.CREATE]
    totals = Counter((r.status, r.outcome) for r in created)

    assert totals == {
        (ItemStatus.APPROVED, DecisionOutcome.APPROVED): 125,
        (ItemStatus.APPROVED, DecisionOutcome.APPROVED_WITH_EDITS): 14,
        (ItemStatus.CHANGES_REQUESTED, DecisionOutcome.CHANGES_REQUESTED): 10,
        (ItemStatus.IN_REVIEW, None): 12,
        (ItemStatus.REJECTED, DecisionOutcome.REJECTED): 9,
        (ItemStatus.SUBMITTED, None): 8,
    }
    open_rows = [r for r in created if r.status in {ItemStatus.SUBMITTED, ItemStatus.IN_REVIEW}]
    assert len(open_rows) == 20
    assert sum(1 for r in open_rows if r.reviewer is None) == 8


def test_readme_totals_are_the_ones_asserted_here() -> None:
    # If the generator changes the sample, the hard-coded totals above must change with it.
    text = oracle.readme()
    assert "**Items after import: 178**, with 177 distinct Request IDs" in text
    assert "Open (submitted or in review) on 2026-08-14: 20; unassigned: 8." in text
    assert "| approved (decision: approved) | 125 |" in text


# --- intended messiness, table by table ------------------------------------------------------------------------

_DECISION = re.compile(r"decision: (\w+)")


@pytest.mark.parametrize("mess", oracle.mess("Status spelling variants"), ids=_ids)
def test_status_spelling_variants(result: NormalizedImport, mess: oracle.MessRow) -> None:
    row = _by_row(result)[mess.rows[0]]

    assert row.source_ref == mess.request_id
    assert (row.status, row.outcome) == _canonical_status(mess.expected)
    if "warning" in mess.expected:
        assert (K.INFERRED_STATUS, S.WARNING) in _kinds(row)


@pytest.mark.parametrize("mess", oracle.mess("Product spelling variants"), ids=_ids)
def test_product_spelling_variants(result: NormalizedImport, mess: oracle.MessRow) -> None:
    assert _by_row(result)[mess.rows[0]].product == Product(mess.expected)


@pytest.mark.parametrize(
    "mess", oracle.mess("Date Submitted stored as text") + oracle.mess("Expiration stored as text"), ids=_ids
)
def test_dates_stored_as_text_are_coerced_and_noted(result: NormalizedImport, mess: oracle.MessRow) -> None:
    row = _by_row(result)[mess.rows[0]]
    value = row.submitted_on if mess.column == "Date Submitted" else row.expires_on

    assert value == date.fromisoformat(mess.expected[:10])
    coerced = [p for p in row.problems if p.kind is K.COERCED_DATE and p.column == mess.column]
    assert [(p.severity, p.value) for p in coerced] == [(S.INFO, mess.raw)]


_APPROVER = re.compile(r"approver (?P<name>.+?); date (?P<date>\d{4}-\d{2}-\d{2})")


@pytest.mark.parametrize("mess", oracle.mess("Approval cell with approver only (no date)"), ids=_ids)
def test_approver_only_takes_the_date_from_the_last_round(result: NormalizedImport, mess: oracle.MessRow) -> None:
    row = _by_row(result)[mess.rows[0]]
    expected = _APPROVER.match(mess.expected)
    assert expected is not None

    assert row.approver == expected.group("name")
    assert row.approved_on == date.fromisoformat(expected.group("date"))
    assert row.approval_derived
    assert (K.DERIVED_APPROVAL_DATE, S.WARNING) in _kinds(row)
    assert row.timeline is not None
    assert row.timeline.decided_at == datetime.fromisoformat(expected.group("date")).replace(tzinfo=UTC)


@pytest.mark.parametrize("mess", oracle.mess("Approved row with blank expiration"), ids=_ids)
def test_approved_with_blank_expiration_stays_null(result: NormalizedImport, mess: oracle.MessRow) -> None:
    row = _by_row(result)[mess.rows[0]]

    assert row.status is ItemStatus.APPROVED
    assert row.expires_on is None
    assert (K.MISSING_EXPIRY, S.WARNING) in _kinds(row)


def test_missing_expiry_is_reported_on_exactly_the_oracle_rows(result: NormalizedImport) -> None:
    flagged = {r.row_number for r in result.rows if (K.MISSING_EXPIRY, S.WARNING) in _kinds(r)}

    assert flagged == {m.rows[0] for m in oracle.mess("Approved row with blank expiration")}


def test_exact_duplicate_row_is_one_item(result: NormalizedImport) -> None:
    (mess,) = oracle.mess("Exact duplicate row")
    first, second = (_by_row(result)[n] for n in mess.rows)

    assert first.action is RowAction.CREATE
    assert second.action is RowAction.SKIP_DUPLICATE
    assert second.duplicate_of == first.row_number
    assert [p.kind for p in second.problems] == [K.DUPLICATE_ROW]


def test_reused_request_id_is_two_items_with_a_disambiguated_ref(result: NormalizedImport) -> None:
    (mess,) = oracle.mess("Request ID reused for a different asset")
    first, second = (_by_row(result)[n] for n in mess.rows)

    assert (first.action, second.action) == (RowAction.CREATE, RowAction.CREATE)
    assert (first.legacy_ref, second.legacy_ref) == (mess.request_id, f"{mess.request_id}-b")
    assert (first.submitted_on, second.submitted_on) == (date(2026, 5, 26), date(2026, 5, 27))
    assert (K.REUSED_REF, S.WARNING) in _kinds(second)
    assert (K.REUSED_REF, S.WARNING) not in _kinds(first)


_STRIPPED = re.compile(r'^"(?P<value>.*)" after strip\(\)$')


def _field(row: ParsedRow, target: ImportTargetField) -> object:
    return {
        T.LEGACY_REF: row.source_ref,
        T.PARTNER: row.partner_name,
        T.REVIEWER: row.reviewer,
        T.SUBMITTER: row.submitter,
        T.PRODUCT: row.product,
        T.CHANNEL: row.channel,
    }[target]


@pytest.mark.parametrize("mess", oracle.mess("Leading / trailing whitespace"), ids=_ids)
def test_every_string_cell_is_stripped(result: NormalizedImport, mess: oracle.MessRow) -> None:
    row = _by_row(result)[mess.rows[0]]
    expected = _STRIPPED.match(mess.expected)
    target = guess_target(mess.column)
    assert expected is not None
    assert target is not None
    want = expected.group("value")

    if target is T.PRODUCT:
        assert row.product == PRODUCT_MAP[value_key(want)]
    elif target is T.CHANNEL:
        assert row.channel == Channel(want.lower().replace(" ", "_"))
    else:
        assert _field(row, target) == want


@pytest.mark.parametrize("mess", oracle.mess("Partner typed differently from the Partners sheet"), ids=_ids)
def test_partner_typed_differently_resolves_and_is_reported(result: NormalizedImport, mess: oracle.MessRow) -> None:
    row = _by_row(result)[mess.rows[0]]

    assert row.partner_name == mess.expected.removeprefix("partner ").strip("'")
    assert (K.FUZZY_PARTNER, S.WARNING) in _kinds(row)


@pytest.mark.parametrize("mess", oracle.mess("Trigger Terms Y/N variants"), ids=_ids)
def test_trigger_terms_variants(result: NormalizedImport, mess: oracle.MessRow) -> None:
    row = _by_row(result)[mess.rows[0]]
    expected = {"true": True, "false": False, "null": None}[mess.expected.split()[0]]

    assert row.trigger_terms is expected
    if expected is None:
        assert (K.UNKNOWN_TRIGGER_TERMS, S.WARNING) in _kinds(row)


def test_merged_note_row_is_skipped_and_reported(result: NormalizedImport) -> None:
    (mess,) = oracle.mess("Merged note row inside the data")
    row = _by_row(result)[mess.rows[0]]

    assert row.action is RowAction.SKIP_NOT_DATA
    assert row.legacy_ref is None
    assert [(p.kind, p.column) for p in row.problems] == [(K.NOT_DATA_ROW, "Request ID")]


# --- links -----------------------------------------------------------------------------------------------------


def test_asset_links_from_hyperlinks_text_or_nothing(result: NormalizedImport, sample_workbook: RawWorkbook) -> None:
    rows = _by_row(result)
    raw = {r.row_number: r.cells[5] for r in sample_workbook.tracker.rows}
    hyperlinked = oracle.link_rows("Asset Name / File Link", "hyperlinked cells")
    text_url = oracle.link_rows("Asset Name / File Link", "Text containing a URL")
    no_link = oracle.link_rows("Asset Name / File Link", "Asset name only")

    assert (len(hyperlinked), len(text_url), len(no_link)) == (96, 58, 25)
    for n in hyperlinked:
        assert rows[n].asset_url == raw[n].hyperlink
        assert rows[n].title == raw[n].text
    for n in text_url:
        assert raw[n].hyperlink is None
        url = rows[n].asset_url
        assert url is not None
        assert url.startswith("https://sharepoint.clearpath.example/")
        assert rows[n].title
        assert "https://" not in (rows[n].title or "")
    for n in no_link:
        assert rows[n].asset_url is None
        assert rows[n].title == raw[n].text


def test_placement_links_from_hyperlinks_and_text(result: NormalizedImport, sample_workbook: RawWorkbook) -> None:
    rows = _by_row(result)
    raw = {r.row_number: r.cells[16] for r in sample_workbook.tracker.rows}
    hyperlinked = oracle.link_rows("Live URL / Placement & Screenshot Link", "hyperlinked cells")
    labelled = oracle.link_rows("Live URL / Placement & Screenshot Link", "Display text differs")
    text_url = oracle.link_rows("Live URL / Placement & Screenshot Link", "Text containing a URL")

    assert (len(hyperlinked), len(text_url)) == (7, 87)
    for n in hyperlinked:
        assert rows[n].placement_urls[0] == raw[n].hyperlink
    for n in labelled:
        assert rows[n].placement != rows[n].placement_urls[0]
    for n in text_url:
        assert rows[n].placement_urls
        assert all(u.startswith("https://") for u in rows[n].placement_urls)


# --- every raw value, mapped -----------------------------------------------------------------------------------


def _raw_counts(sample_workbook: RawWorkbook, column: str) -> list[tuple[int, str | None]]:
    i = sample_workbook.tracker.headers.index(column)
    return [(r.row_number, r.cells[i].text) for r in sample_workbook.tracker.rows if r.row_number != 43]


def _canonical_status(text: str) -> tuple[ItemStatus, DecisionOutcome | None]:
    decision = _DECISION.search(text)
    status = ItemStatus(text.split(maxsplit=1)[0])
    if status is ItemStatus.CHANGES_REQUESTED:
        return status, DecisionOutcome.CHANGES_REQUESTED
    return status, DecisionOutcome(decision.group(1)) if decision else None


@pytest.mark.parametrize("value", oracle.raw_values("Status values"), ids=lambda v: f"{v.raw!r}->{v.canonical}")
def test_every_status_value(result: NormalizedImport, sample_workbook: RawWorkbook, value: oracle.RawValueRow) -> None:
    rows = _by_row(result)
    want = _canonical_status(value.canonical)
    # Raw cells are stripped on read, so "approved " arrives as "approved".
    raw = value.raw.strip() if value.raw else None
    hits = [n for n, text in _raw_counts(sample_workbook, "Status") if text == raw]

    assert sum(1 for n in hits if (rows[n].status, rows[n].outcome) == want) == value.count


@pytest.mark.parametrize("value", oracle.raw_values("Product values"), ids=lambda v: f"{v.raw!r}->{v.canonical}")
def test_every_product_value(result: NormalizedImport, sample_workbook: RawWorkbook, value: oracle.RawValueRow) -> None:
    rows = _by_row(result)
    raw = (value.raw or "").strip()  # cells are stripped on read: " Credit Card" and "Credit Card" meet here
    hits = [n for n, text in _raw_counts(sample_workbook, "Product") if text == raw]
    same_raw = sum(v.count for v in oracle.raw_values("Product values") if (v.raw or "").strip() == raw)

    assert len(hits) == same_raw
    assert {rows[n].product for n in hits} == {Product(value.canonical)}


@pytest.mark.parametrize("value", oracle.raw_values("Trigger Terms values"), ids=lambda v: f"{v.raw!r}->{v.canonical}")
def test_every_trigger_terms_value(
    result: NormalizedImport, sample_workbook: RawWorkbook, value: oracle.RawValueRow
) -> None:
    rows = _by_row(result)
    hits = [n for n, text in _raw_counts(sample_workbook, "Trigger Terms Present (Y/N)") if text == value.raw]
    # Blank and "?" are stored as unknown even though the generator's truth (the Canonical column) is known.
    want = None if value.raw in {None, "?"} else value.canonical == "Y"
    same_raw = sum(v.count for v in oracle.raw_values("Trigger Terms values") if v.raw == value.raw)

    assert len(hits) == same_raw
    assert {rows[n].trigger_terms for n in hits} == {want}


@pytest.mark.parametrize("value", oracle.raw_values("Partner values"), ids=lambda v: f"{v.raw!r}->{v.canonical}")
def test_every_partner_value(result: NormalizedImport, sample_workbook: RawWorkbook, value: oracle.RawValueRow) -> None:
    rows = _by_row(result)
    raw = value.raw.strip() if value.raw else None
    hits = [n for n, text in _raw_counts(sample_workbook, "Affiliate / Partner") if text == raw]
    want = None if value.canonical == "(none)" else value.canonical
    same_raw = sum(v.count for v in oracle.raw_values("Partner values") if (v.raw.strip() if v.raw else None) == raw)

    assert len(hits) == same_raw
    assert {rows[n].partner_name for n in hits} == {want}


# --- other characteristics -------------------------------------------------------------------------------------


def test_comments_that_cross_new_year_roll_the_year(result: NormalizedImport) -> None:
    rows = _by_row(result)
    crossing = oracle.bullet_rows("Comments that cross New Year")

    assert crossing
    for n in crossing:
        years = [s.on.year for s in rows[n].segments]
        assert years == sorted(years)
        assert years[-1] == 2026
        submitted = rows[n].submitted_on
        assert submitted is not None
        assert submitted.year == 2025
    assert [s.on for s in rows[37].segments] == [date(2025, 12, 11), date(2025, 12, 17), date(2026, 1, 5)]


def test_approval_date_equals_the_last_round_on_every_approved_row(result: NormalizedImport) -> None:
    approved = [r for r in result.rows if r.action is RowAction.CREATE and r.status is ItemStatus.APPROVED]

    assert len(approved) == 139
    for row in approved:
        assert row.segments, row.legacy_ref
        assert row.approved_on == row.segments[-1].on, row.legacy_ref
        assert row.approver is not None
        assert row.approver.split()[-1] in {"Kim", "Ortega", "Brandt", "Rao", "Okafor"}


def test_rounds_follow_the_comment_segments(result: NormalizedImport) -> None:
    for row in (r for r in result.rows if r.action is RowAction.CREATE):
        n = len(row.segments)
        assert row.rounds in {max(n, 1), n + 1}, row.legacy_ref
        if n and row.rounds == n + 1:
            assert row.status is ItemStatus.IN_REVIEW
    five = oracle.bullet_rows("Five-round items")
    assert {_by_row(result)[n].rounds for n in five} == {5}


def test_every_created_row_has_an_ordered_timeline(result: NormalizedImport) -> None:
    for row in (r for r in result.rows if r.action is RowAction.CREATE):
        t = row.timeline
        assert t is not None, row.legacy_ref
        assert t.submitted_at is not None
        assert t.rounds == row.rounds
        if row.status in {ItemStatus.APPROVED, ItemStatus.REJECTED, ItemStatus.CHANGES_REQUESTED}:
            assert t.decided_at is not None
            assert t.outcome == row.outcome
        else:
            assert (t.decided_at, t.outcome) == (None, None)


def test_hand_offs_keep_the_assigned_reviewer(result: NormalizedImport) -> None:
    rows = _by_row(result)
    for n in oracle.bullet_rows("Reviewer hand-offs"):
        assert len({s.initials for s in rows[n].segments}) > 1
        assert rows[n].reviewer is not None


# --- what the admin can fix ------------------------------------------------------------------------------------


def test_unknown_status_is_a_problem_until_mapped(sample_workbook: RawWorkbook) -> None:
    wb = _with_cell(sample_workbook, 2, "Status", RawCell(text="On hold"))

    before = _run(wb)
    row = _by_row(before)[2]
    assert row.action is RowAction.BLOCKED
    assert (K.UNMAPPED_STATUS, S.ERROR) in _kinds(row)
    assert [(u.field, u.value, u.rows) for u in before.unmapped] == [(T.STATUS, "On hold", 1)]
    assert before.counts.blocked == 1

    mapping = ImportMapping(
        columns=guess_column_mapping(wb.tracker.headers),
        statuses=(StatusOverride("on HOLD ", ItemStatus.SUBMITTED, None),),
    )
    after = _by_row(_run(wb, mapping))[2]
    assert after.action is RowAction.CREATE
    assert after.status is ItemStatus.SUBMITTED


def test_unknown_product_and_partner_block_until_mapped(sample_workbook: RawWorkbook) -> None:
    wb = _with_cell(sample_workbook, 2, "Product", RawCell(text="Auto Loan"))
    wb = _with_cell(wb, 2, "Affiliate / Partner", RawCell(text="Brand New Blog"))

    before = _by_row(_run(wb))[2]
    assert before.action is RowAction.BLOCKED
    assert {(K.UNKNOWN_VALUE, S.ERROR), (K.UNKNOWN_PARTNER, S.ERROR)} <= _kinds(before)

    mapping = ImportMapping(
        columns=guess_column_mapping(wb.tracker.headers),
        values=(
            ValueOverride(ImportValueField.PRODUCT, "auto loan", Product.PERSONAL_LOAN.value),
            ValueOverride(ImportValueField.PARTNER, "Brand New Blog", "RateRadar"),
        ),
    )
    after = _by_row(_run(wb, mapping))[2]
    assert after.action is RowAction.CREATE
    assert (after.product, after.partner_name) == (Product.PERSONAL_LOAN, "RateRadar")


def test_missing_required_mapping_is_a_sheet_problem(sample_workbook: RawWorkbook) -> None:
    columns = guess_column_mapping(sample_workbook.tracker.headers)
    columns["Request ID"] = T.IGNORE

    out = _run(sample_workbook, ImportMapping(columns=columns))

    assert out.rows == ()
    assert [(p.kind, p.message) for p in out.problems] == [(K.MISSING_MAPPING, "Map a column to Request ID.")]


def test_refs_already_in_the_app_are_skipped(sample_workbook: RawWorkbook) -> None:
    out = _run(sample_workbook, existing_refs=frozenset({"MCR-25-001", "MCR-26-077-b"}))
    rows = _by_row(out)

    assert rows[2].action is RowAction.SKIP_ALREADY_IMPORTED
    assert rows[122].action is RowAction.SKIP_ALREADY_IMPORTED
    assert rows[121].action is RowAction.CREATE
    assert out.counts.ready == 176
    assert out.counts.already_imported == 2


def test_approval_dated_before_submission_blocks_the_row(sample_workbook: RawWorkbook) -> None:
    # Round dates roll forward from the submission year, so only an explicit approval date can precede it.
    wb = _with_cell(sample_workbook, 2, "Approval Date & Approver", RawCell(text="8/1/25 - L. Brandt"))

    row = _by_row(_run(wb))[2]

    assert row.action is RowAction.BLOCKED
    assert (K.INCONSISTENT_DATES, S.ERROR) in _kinds(row)


# --- cell parsers ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "hint", "expected"),
    [
        ("11/19/25", None, date(2025, 11, 19)),
        ("3/21/2027", None, date(2027, 3, 21)),
        ("2026-03-16", None, date(2026, 3, 16)),
        ("Dec 1", 2025, date(2025, 12, 1)),
        ("Jan 28", 2026, date(2026, 1, 28)),
        ("Jan 28", None, None),
        ("2/30/26", None, None),
        ("soon", 2026, None),
    ],
)
def test_parse_date(text: str, hint: int | None, expected: date | None) -> None:
    parsed = parse_date(RawCell(text=text), year_hint=hint)

    assert parsed.on == expected
    assert parsed.failed is (expected is None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("L. Brandt", "Leah Brandt"), ("l brandt", "Leah Brandt"), ("Dana Kim", "Dana Kim"), ("X. Nobody", None)],
)
def test_resolve_person(raw: str, expected: str | None) -> None:
    assert resolve_person(raw, ["Dana Kim", "Leah Brandt", "Nikhil Rao"]) == expected


def test_resolve_person_refuses_an_ambiguous_initial() -> None:
    assert resolve_person("D. Kim", ["Dana Kim", "Dev Kim"]) is None


def test_split_asset_shapes() -> None:
    url = "https://sharepoint.clearpath.example/a/MTG_LP_v4.pdf"

    assert split_asset(RawCell(text=f"MTG landing page - {url}")) == ("MTG landing page", url)
    assert split_asset(RawCell(text="CC search ads (emailed 1/16)")) == ("CC search ads (emailed 1/16)", None)
    assert split_asset(RawCell(text="file.pdf", hyperlink=url)) == ("file.pdf", url)
    assert split_asset(RawCell(text=url)) == ("MTG_LP_v4.pdf", url)


def test_partner_directory_prefers_app_spelling_and_needs_a_unique_prefix() -> None:
    directory = PartnerDirectory.build(existing=["Lendcompare"], sheet=["LendCompare", "CardPerks Weekly", "CardSmart"])

    assert directory.resolve("Lend Compare") is not None
    assert directory.resolve("Lend Compare").name == "Lendcompare"  # pyrefly: ignore[missing-attribute]
    assert directory.resolve("CardPerks").name == "CardPerks Weekly"  # pyrefly: ignore[missing-attribute]
    assert directory.resolve("Card") is None  # two partners start with "card"
    assert directory.resolve("LendCompare").fuzzy is True  # pyrefly: ignore[missing-attribute]  # app spelling differs


def test_partner_prefix_needs_four_characters() -> None:
    directory = PartnerDirectory.build(existing=[], sheet=["RateRadar", "LendCompare"])

    assert directory.resolve("R") is None
    assert directory.resolve("Rat") is None
    assert directory.resolve("Rate") == PartnerMatch(name="RateRadar", fuzzy=True)


def test_a_date_serial_in_a_general_cell_is_a_date() -> None:
    parsed = parse_date(RawCell(number=46023), year_hint=None)

    assert (parsed.on, parsed.coerced) == (date(2026, 1, 1), True)
    assert parse_date(RawCell(number=3), year_hint=None).failed


def test_only_web_links_are_kept() -> None:
    assert split_asset(RawCell(text="memo.pdf", hyperlink="file:///C:/memo.pdf")) == ("memo.pdf", None)
    assert split_asset(RawCell(text="memo.pdf", hyperlink="javascript:alert(1)")) == ("memo.pdf", None)


def test_a_ref_shaped_cell_on_an_otherwise_blank_row_is_not_data(sample_workbook: RawWorkbook) -> None:
    wb = _with_cell(sample_workbook, 43, "Request ID", RawCell(text="179"))

    assert _by_row(_run(wb))[43].action is RowAction.SKIP_NOT_DATA


def test_approvers_resolve_from_the_reviewer_column_without_a_lists_sheet(sample_workbook: RawWorkbook) -> None:
    out = _run(sample_workbook.model_copy(update={"reviewers": ()}))

    assert not [p for p in out.all_problems if p.kind is K.UNRESOLVED_APPROVER]
    assert _by_row(out)[2].approver == "Leah Brandt"
