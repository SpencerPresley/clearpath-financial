"""Walkthrough B1: fast-track never approves an item whose live page doesn't show the approved copy.

A terms change on a drift re-review generates a fast-track version (the approved text with the new numbers), but
the partner page still shows something else: fast-tracking would approve content that isn't what's live. Refused
(`drift_not_restored`) until a check finds the approved copy again, single and bulk alike.
"""

import pytest
from django.db import transaction

from accounts.models import User
from core.clock import FixedClock
from core.domain import ItemStatus, ReopenReason, VersionOrigin
from core.errors import Conflict
from drift import services
from drift.tests.conftest import page_with
from drift.tests.test_services import EDITED, check
from reviews.assignment import locked_item
from reviews.errors import DriftNotRestored
from reviews.models import Decision, Placement, ReviewItem
from reviews.records import get_item_detail
from reviews.rereview import send_back
from reviews.selectors import DriftRereview, get_item_row
from reviews.versions import create_version
from terms.fast_track import bulk_fast_track_approve, fast_track_approve

pytestmark = pytest.mark.django_db

NEW_NUMBERS = "Personal loans from ClearPath. Apply online in minutes today."


def _generate(item_id: int, lead: User, clock: FixedClock) -> int:
    """What the terms fan-out does to an item already in re-review: a fast-track version from the approved text."""
    item = locked_item(item_id)
    approved = item.current_version
    assert approved is not None
    version = create_version(
        item=item, text=NEW_NUMBERS, author=lead, origin=VersionOrigin.FAST_TRACK, based_on=approved, clock=clock
    ).version
    return version.n


@pytest.fixture
def drifted(placement: Placement, clock: FixedClock, enqueued: list[int]) -> ReviewItem:
    services.complete(claim=check(placement, clock), page=page_with(EDITED), clock=clock)
    item = ReviewItem.objects.get(pk=placement.item_id)  # pyrefly: ignore[missing-attribute]
    assert (item.status, item.reopen_reason) == (ItemStatus.NEEDS_REREVIEW, ReopenReason.DRIFT_DETECTED)
    return item


def test_fast_track_is_refused_while_the_drift_is_unresolved(
    drifted: ReviewItem, placement: Placement, reviewer: User, lead: User, clock: FixedClock
) -> None:
    n = _generate(drifted.pk, lead, clock)

    with pytest.raises(DriftNotRestored) as refused:
        fast_track_approve(actor=reviewer, item_id=drifted.pk, version_n=n, reason="Only numbers changed", clock=clock)

    assert refused.value.details == {"placement_id": placement.pk}
    assert ReviewItem.objects.get(pk=drifted.pk).status == ItemStatus.NEEDS_REREVIEW
    assert not Decision.objects.filter(item=drifted, lane="fast_track").exists()


def test_bulk_fast_track_skips_the_drifted_item_with_the_reason(
    drifted: ReviewItem, reviewer: User, lead: User, clock: FixedClock
) -> None:
    n = _generate(drifted.pk, lead, clock)

    result = bulk_fast_track_approve(
        actor=lead, item_ids=[drifted.pk], reason="Only numbers changed", seen_versions={drifted.pk: n}, clock=clock
    )

    assert result.succeeded == ()
    [skip] = result.skipped
    assert (skip.item_id, skip.code) == (drifted.pk, "drift_not_restored")
    assert "doesn't show the approved copy" in skip.message


def test_fast_track_is_allowed_once_a_check_finds_the_copy_restored(
    drifted: ReviewItem, placement: Placement, reviewer: User, lead: User, clock: FixedClock
) -> None:
    n = _generate(drifted.pk, lead, clock)
    services.complete(claim=check(placement, clock), page=page_with(), clock=clock)

    fast_track_approve(actor=reviewer, item_id=drifted.pk, version_n=n, reason="Restored; new numbers", clock=clock)

    assert ReviewItem.objects.get(pk=drifted.pk).status == ItemStatus.APPROVED


def test_a_terms_rereview_whose_page_then_changed_is_refused_too(
    placement: Placement, reviewer: User, lead: User, clock: FixedClock, enqueued: list[int]
) -> None:
    item_id = placement.item_id  # pyrefly: ignore[missing-attribute]
    send_back(item_id=item_id, reason=ReopenReason.TERMS_CHANGED, clock=clock)
    n = _generate(item_id, lead, clock)
    # The daily check finds the page changed; the item is already in re-review, so it isn't sent back again.
    services.complete(claim=check(placement, clock), page=page_with(EDITED), clock=clock)
    assert ReviewItem.objects.get(pk=item_id).reopen_reason == ReopenReason.TERMS_CHANGED

    assert get_item_detail(item_id=item_id, clock=clock).drift_rereview == DriftRereview(
        placement_id=placement.pk, restored=False
    )
    with pytest.raises(DriftNotRestored):
        fast_track_approve(actor=reviewer, item_id=item_id, version_n=n, reason="Only numbers changed", clock=clock)


# --- the row flag: fast_track_eligible, the same rule as the lane --------------------------------------------------


def _eligible(item_id: int, clock: FixedClock) -> bool:
    return get_item_row(item_id=item_id, clock=clock).fast_track_eligible


def _lane_allows(item_id: int, n: int, reviewer: User, clock: FixedClock) -> bool:
    """Whether the fast-track lane accepts the item, without keeping the decision."""
    try:
        with transaction.atomic():
            fast_track_approve(actor=reviewer, item_id=item_id, version_n=n, reason="probe", clock=clock)
            transaction.set_rollback(True)
    except (DriftNotRestored, Conflict):
        return False
    return True


def test_the_row_flag_matches_the_lane_through_drift_and_restore(
    drifted: ReviewItem, placement: Placement, reviewer: User, lead: User, clock: FixedClock
) -> None:
    current = drifted.current_version.n  # pyrefly: ignore[missing-attribute]
    assert _eligible(drifted.pk, clock) is _lane_allows(drifted.pk, current, reviewer, clock) is False  # not generated

    n = _generate(drifted.pk, lead, clock)
    assert _eligible(drifted.pk, clock) is _lane_allows(drifted.pk, n, reviewer, clock) is False  # page differs

    services.complete(claim=check(placement, clock), page=page_with(), clock=clock)
    assert _eligible(drifted.pk, clock) is _lane_allows(drifted.pk, n, reviewer, clock) is True  # restored


def test_the_row_flag_is_off_for_a_terms_rereview_whose_page_changed(
    placement: Placement, reviewer: User, lead: User, clock: FixedClock, enqueued: list[int]
) -> None:
    item_id = placement.item_id  # pyrefly: ignore[missing-attribute]
    send_back(item_id=item_id, reason=ReopenReason.TERMS_CHANGED, clock=clock)
    n = _generate(item_id, lead, clock)
    assert _eligible(item_id, clock) is _lane_allows(item_id, n, reviewer, clock) is True

    services.complete(claim=check(placement, clock), page=page_with(EDITED), clock=clock)
    assert _eligible(item_id, clock) is _lane_allows(item_id, n, reviewer, clock) is False


def test_only_a_rereview_can_be_eligible(placement: Placement, clock: FixedClock) -> None:
    item_id = placement.item_id  # pyrefly: ignore[missing-attribute]
    assert ReviewItem.objects.get(pk=item_id).status == ItemStatus.APPROVED
    assert _eligible(item_id, clock) is False
