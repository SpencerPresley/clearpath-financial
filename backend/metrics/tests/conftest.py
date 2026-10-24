"""Metrics fixtures: items driven through the real review services, and imported tracker rows."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.db import transaction

from accounts.models import User
from audit.payloads import ItemImportedPayload, LegacyTimeline
from audit.services import record_event
from core.clock import FixedClock
from core.domain import DecisionOutcome, EntityType, EventType, ItemStatus, Product
from reviews.models import ReviewItem
from reviews.tests.conftest import approve, pl_terms, submit  # noqa: F401  # re-exported fixtures
from reviews.tests.factories import make_item


def midnight(on: date) -> datetime:
    return datetime(on.year, on.month, on.day, tzinfo=UTC)


def import_row(
    ref: str,
    *,
    submitted: date,
    first_reviewed: date | None = None,
    decided: date | None = None,
    outcome: DecisionOutcome | None = None,
    rounds: int | None = 1,
    product: Product = Product.PERSONAL_LOAN,
    clock: FixedClock,
) -> ReviewItem:
    """A legacy item and its ITEM_IMPORTED event, as G's commit writes them (event time = import time)."""
    status = (
        ItemStatus.APPROVED
        if outcome in (DecisionOutcome.APPROVED, DecisionOutcome.APPROVED_WITH_EDITS)
        else ItemStatus.SUBMITTED
    )
    with transaction.atomic():
        item = make_item(
            None,
            is_legacy=True,
            legacy_ref=ref,
            status=status,
            product=product,
            markets=[],
            submitted_at=midnight(submitted),
        )
        record_event(
            type=EventType.ITEM_IMPORTED,
            entity=EntityType.ITEM,
            entity_id=item.pk,
            item_id=item.pk,
            payload=ItemImportedPayload(
                import_id=1,
                legacy_ref=ref,
                row_number=2,
                timeline=LegacyTimeline(
                    submitted_at=midnight(submitted),
                    first_reviewed_at=midnight(first_reviewed) if first_reviewed else None,
                    decided_at=midnight(decided) if decided else None,
                    outcome=outcome,
                    rounds=rounds,
                ),
            ),
            actor=None,
            at=clock.now(),
            to_status=status,
        )
    return item


@pytest.fixture
def two_round_item(submit, reviewer: User, marketer: User, clock: FixedClock) -> ReviewItem:  # noqa: F811
    """Submitted at T, review started at T+5h, changes requested at T+8h, resubmitted at T+30h, approved at
    T+34h. T is 3 days before the test clock's start."""
    from reviews.assignment import claim_item
    from reviews.decisions import DecisionInput, record_decision
    from reviews.versions import resubmit_item

    start = clock.now()
    clock.advance(timedelta(days=-3))
    item_id = submit(title="Two rounds").item_id
    clock.advance(timedelta(hours=5))
    claim_item(actor=reviewer, item_id=item_id, clock=clock)
    clock.advance(timedelta(hours=3))
    record_decision(
        actor=reviewer,
        item_id=item_id,
        data=DecisionInput(outcome=DecisionOutcome.CHANGES_REQUESTED, version_n=1, reason="Add the APR range"),
        clock=clock,
    )
    clock.advance(timedelta(hours=22))
    resubmit_item(
        actor=marketer, item_id=item_id, content_text="Personal loans from ClearPath. Apply online.", clock=clock
    )
    clock.advance(timedelta(hours=4))
    approve(item_id, reviewer, clock)
    clock.at = start
    return ReviewItem.objects.get(pk=item_id)
