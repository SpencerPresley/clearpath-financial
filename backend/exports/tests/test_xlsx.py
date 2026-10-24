import io
import re
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest

from core.domain import Channel, DecisionOutcome, ItemStatus, Market, Product, RiskTier
from exports.labels import CHANNEL_LABELS, OUTCOME_LABELS, PRODUCT_LABELS, RISK_LABELS, STATUS_LABELS
from exports.xlsx import HEADERS, ExportRow, write_items_xlsx

BADGES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "ui" / "badges.tsx"


def _row(**overrides: object) -> ExportRow:
    fields: dict[str, object] = {
        "key": "CP-12",
        "title": "Spring PL email",
        "status": ItemStatus.NEEDS_REREVIEW,
        "product": Product.PERSONAL_LOAN,
        "channel": Channel.PAID_SOCIAL,
        "partner": "LendCompare",
        "risk_tier": RiskTier.HIGH,
        "round": 2,
        "version_n": 3,
        "markets": (Market.NATIONAL, Market.CA),
        "tags": ("spring", "q2"),
        "submitter": "Morgan Marketer",
        "reviewer": "Dana Kim",
        "open_findings": 0,
        "submitted_on": date(2026, 3, 2),
        "approved_on": date(2026, 3, 9),
        "approval_expires_on": None,
        "legacy_ref": None,
    }
    fields.update(overrides)
    return ExportRow(**fields)  # pyrefly: ignore[bad-argument-type]


def _read(rows: list[ExportRow]) -> list[tuple[object, ...]]:
    buf = io.BytesIO()
    assert write_items_xlsx(rows, buf) == len(rows)
    buf.seek(0)
    ws = openpyxl.load_workbook(buf)["Items"]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == f"A1:R{len(rows) + 1}"
    return [tuple(c.value for c in r) for r in ws.iter_rows()]


def test_headers_and_readable_values() -> None:
    header, row = _read([_row()])

    assert header == HEADERS
    assert header[:7] == ("Item", "Title", "Status", "Product", "Channel", "Partner", "Risk tier")
    assert row[:10] == (
        "CP-12",
        "Spring PL email",
        "Re-review",
        "Personal loan",
        "Paid social",
        "LendCompare",
        "High",
        2,
        "v3",
        "National, CA",
    )
    assert row[10:] == (
        "spring, q2",
        "Morgan Marketer",
        "Dana Kim",
        0,
        datetime(2026, 3, 2),  # noqa: DTZ001  # xlsx dates have no zone; openpyxl reads them back naive
        datetime(2026, 3, 9),  # noqa: DTZ001
        None,
        None,
    )


def test_empty_view_is_just_the_header() -> None:
    assert _read([]) == [HEADERS]


def test_legacy_rows_keep_their_request_id() -> None:
    (_, row) = _read([_row(version_n=None, legacy_ref="MCR-26-101-b", markets=(), tags=())])

    assert (row[8], row[9], row[10], row[17]) == (None, None, None, "MCR-26-101-b")


def test_every_enum_member_has_a_label() -> None:
    assert set(STATUS_LABELS) == set(ItemStatus)
    assert set(OUTCOME_LABELS) == set(DecisionOutcome)
    assert set(PRODUCT_LABELS) == set(Product)
    assert set(CHANNEL_LABELS) == set(Channel)
    assert set(RISK_LABELS) == set(RiskTier)


@pytest.mark.skipif(not BADGES.exists(), reason="frontend/ is outside the backend image")
def test_status_labels_match_the_ui() -> None:
    block = BADGES.read_text().split("STATUS_META", 1)[1].split("};", 1)[0]
    ui = dict(re.findall(r"(\w+): \{ label: '([^']+)'", block))

    assert ui == {s.value: label for s, label in STATUS_LABELS.items()}
