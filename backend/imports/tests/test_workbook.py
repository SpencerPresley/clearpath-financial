import io
from datetime import UTC, datetime

import pytest

from imports.workbook import RawWorkbook, UnreadableWorkbook, read_workbook


def test_reads_the_tracker_sheet_with_every_row_below_the_header(sample_workbook: RawWorkbook) -> None:
    tracker = sample_workbook.tracker

    assert tracker.name == "Review Tracker"
    assert tracker.header_row == 1
    assert len(tracker.headers) == 17
    assert tracker.headers[0] == "Request ID"
    assert [r.row_number for r in tracker.rows] == list(range(2, 182))


def test_cells_keep_hyperlink_targets_dates_numbers_and_stripped_text(sample_workbook: RawWorkbook) -> None:
    rows = {r.row_number: r for r in sample_workbook.tracker.rows}
    r34 = rows[34].cells

    assert r34[5].text == "CC_CashBackCard_EM_v1.pdf"
    assert r34[5].hyperlink == (
        "https://sharepoint.clearpath.example/sites/MarketingCompliance/Submissions/MCR-26-015/CC_CashBackCard_EM_v1.pdf"
    )
    assert r34[1].when == datetime(2026, 2, 4, tzinfo=UTC)
    assert r34[10].number == 1
    assert r34[12].is_empty  # blank Status
    assert rows[150].cells[0].text == "MCR-26-129"  # "MCR-26-129 " stripped
    assert rows[19].cells[0].text is not None
    assert rows[19].cells[0].text.startswith("NOTE (R. Okafor 1/5/26)")


def test_reads_the_partner_directory_and_reviewer_names(sample_workbook: RawWorkbook) -> None:
    partners = {p.name: p for p in sample_workbook.partners}

    assert len(partners) == 8
    assert partners["CardPerks Weekly"].type == "Affiliate"
    assert partners["LendCompare"].agreement_date is not None
    assert partners["LendCompare"].agreement_date.isoformat() == "2024-03-18"
    assert "Nikhil Rao" in sample_workbook.reviewers
    assert len(sample_workbook.reviewers) == 5


def test_round_trips_through_json(sample_workbook: RawWorkbook) -> None:
    assert RawWorkbook.model_validate_json(sample_workbook.model_dump_json()) == sample_workbook


@pytest.mark.parametrize("data", [b"PK...", b"Request ID,Status\nMCR-25-001,Approved\n", b""])
def test_rejects_files_that_are_not_xlsx(data: bytes) -> None:
    with pytest.raises(UnreadableWorkbook, match=r"isn't an \.xlsx workbook"):
        read_workbook(io.BytesIO(data))


def test_rejects_a_workbook_without_tracker_columns() -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Fruit", "Colour", "Weight"])
    ws.append(["Apple", "Red", 1])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    with pytest.raises(UnreadableWorkbook, match="No sheet has tracker columns"):
        read_workbook(buf)
