import io
import time
import zipfile
from datetime import UTC, datetime

import openpyxl
import pytest

from imports.workbook import RawWorkbook, UnreadableWorkbookError, read_workbook


def test_reads_the_tracker_sheet_with_every_row_below_the_header(sample_workbook: RawWorkbook) -> None:
    tracker = sample_workbook.tracker

    assert tracker.name == "Review Tracker"
    assert tracker.header_row == 1
    assert len(tracker.headers) == 17
    assert tracker.headers[0] == "Request ID"
    assert [r.row_number for r in tracker.rows] == list(range(2, 182))


def test_cells_keep_hyperlink_targets_dates_numbers_and_stripped_text(sample_workbook: RawWorkbook) -> None:
    rows = {r.row_number: r for r in sample_workbook.tracker.rows}
    r150 = rows[150].cells

    assert r150[5].text == "CardperksWeekly_CC_NoAnnualFee_AFF_v2.pdf"
    assert r150[5].hyperlink == (
        "https://sharepoint.clearpath.example/sites/MarketingCompliance/Submissions/MCR-26-105/"
        "CardperksWeekly_CC_NoAnnualFee_AFF_v2.pdf"
    )
    assert r150[1].when == datetime(2026, 7, 15, tzinfo=UTC)
    assert r150[10].number == 2
    assert rows[153].cells[12].is_empty  # blank Status
    assert rows[63].cells[0].text == "MCR-26-020"  # "MCR-26-020 " stripped
    assert rows[43].cells[0].text is not None
    assert rows[43].cells[0].text.startswith("NOTE (R. Okafor 1/5/26)")


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
    with pytest.raises(UnreadableWorkbookError, match=r"isn't an \.xlsx workbook"):
        read_workbook(io.BytesIO(data))


def _xlsx(rows: list[list[object]], stray: tuple[int, int] | None = None) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    if stray is not None:
        ws.cell(row=stray[0], column=stray[1], value=" ")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


_TRACKER: list[list[object]] = [
    ["Request ID", "Date Submitted", "Status", "Product"],
    ["MCR-26-001", "2026-01-05", "Approved", "PL"],
]


def test_rejects_a_workbook_without_tracker_columns() -> None:
    with pytest.raises(UnreadableWorkbookError, match="No sheet has tracker columns"):
        read_workbook(_xlsx([["Fruit", "Colour", "Weight"], ["Apple", "Red", 1]]))


def test_a_stray_cell_far_right_and_below_is_not_read() -> None:
    started = time.monotonic()
    wb = read_workbook(_xlsx(_TRACKER, stray=(9000, 300)))

    assert time.monotonic() - started < 3  # read unbounded, this range is 2.7M cells (minutes)
    assert wb.tracker.headers == tuple(_TRACKER[0])
    assert [r.row_number for r in wb.tracker.rows] == [2]


def test_a_used_range_far_below_the_data_is_refused() -> None:
    with pytest.raises(UnreadableWorkbookError, match="has cells down to row 60000"):
        read_workbook(_xlsx(_TRACKER, stray=(60000, 1)))


@pytest.mark.parametrize("part", ["xl/workbook.xml", "xl/worksheets/sheet1.xml", "[Content_Types].xml"])
def test_a_zip_with_broken_xml_is_not_a_workbook(part: str) -> None:
    good = _xlsx(_TRACKER)
    broken = io.BytesIO()
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(broken, "w") as dst:
        for info in src.infolist():
            dst.writestr(info, b"<<<" if info.filename == part else src.read(info))
    broken.seek(0)

    with pytest.raises(UnreadableWorkbookError, match=r"isn't an \.xlsx workbook"):
        read_workbook(broken)
