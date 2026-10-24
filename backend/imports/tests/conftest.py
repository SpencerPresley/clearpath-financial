from functools import cache
from pathlib import Path

import pytest
from pytest_django import Settings

from imports.workbook import SAMPLE_TRACKER_PATH, RawWorkbook, read_workbook


@cache
def _sample() -> RawWorkbook:
    with SAMPLE_TRACKER_PATH.open("rb") as f:
        return read_workbook(f)


@pytest.fixture
def sample_workbook() -> RawWorkbook:
    """The sample tracker, parsed once per session (RawWorkbook is frozen)."""
    return _sample()


@pytest.fixture(autouse=True)
def _media_root(settings: Settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path
