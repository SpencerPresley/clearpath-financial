from functools import cache

import pytest

from imports.workbook import SAMPLE_TRACKER_PATH, RawWorkbook, read_workbook


@cache
def _sample() -> RawWorkbook:
    with SAMPLE_TRACKER_PATH.open("rb") as f:
        return read_workbook(f)


@pytest.fixture
def sample_workbook() -> RawWorkbook:
    """The sample tracker, parsed once per session (RawWorkbook is frozen)."""
    return _sample()
