from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from audit.payloads import ItemImportedPayload, LegacyTimeline, parse_payload
from core.domain import DecisionOutcome, EventType

SUBMITTED = datetime(2025, 3, 3, 9, tzinfo=UTC)
REVIEWED = datetime(2025, 3, 5, 14, tzinfo=UTC)
DECIDED = datetime(2025, 3, 12, 11, tzinfo=UTC)


def test_imported_item_carries_the_trackers_timeline_for_metrics() -> None:
    # The event's occurred_at is the import time; metrics need the tracker's own dates (spec "Metrics").
    payload = ItemImportedPayload(
        import_id=4,
        legacy_ref="REQ-0193",
        row_number=12,
        timeline=LegacyTimeline(
            submitted_at=SUBMITTED,
            first_reviewed_at=REVIEWED,
            decided_at=DECIDED,
            outcome=DecisionOutcome.APPROVED_WITH_EDITS,
            rounds=3,
        ),
    )

    assert parse_payload(EventType.ITEM_IMPORTED, payload.model_dump(mode="json")) == payload


def test_legacy_timeline_fields_are_optional_because_the_tracker_is_messy() -> None:
    assert LegacyTimeline() == LegacyTimeline(
        submitted_at=None, first_reviewed_at=None, decided_at=None, outcome=None, rounds=None
    )


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"submitted_at": DECIDED, "decided_at": SUBMITTED}, "in order"),
        ({"submitted_at": REVIEWED, "first_reviewed_at": SUBMITTED}, "in order"),
        ({"first_reviewed_at": DECIDED, "decided_at": REVIEWED}, "in order"),
        ({"rounds": 0}, "greater than or equal to 1"),
    ],
)
def test_legacy_timeline_rejects_impossible_histories(fields: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        LegacyTimeline.model_validate(fields)
