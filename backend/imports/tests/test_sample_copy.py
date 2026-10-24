"""The backend ships its own copy of the sample tracker (the Docker build context is `backend/`). It must stay
the same workbook as `samples/`, which is the oracle. Compare cell content, not bytes: the generator's openpyxl
save stamps `docProps` and zip entry times on every run (reports/sample-tracker.md item 10)."""

from pathlib import Path

import openpyxl
import pytest

from imports.workbook import SAMPLE_TRACKER_PATH

ORACLE_COPY = Path(__file__).resolve().parents[3] / "samples" / "clearpath_review_tracker.xlsx"

type CellKey = tuple[str, str, object, str | None]


def _cells(path: Path) -> list[CellKey]:
    wb = openpyxl.load_workbook(path)
    return [
        (ws.title, cell.coordinate, cell.value, cell.hyperlink.target if cell.hyperlink else None)
        for ws in wb.worksheets
        for row in ws.iter_rows()
        for cell in row
    ]


@pytest.mark.skipif(not ORACLE_COPY.exists(), reason="samples/ is outside the backend image")
def test_bundled_sample_matches_samples_dir() -> None:
    assert _cells(SAMPLE_TRACKER_PATH) == _cells(ORACLE_COPY)
