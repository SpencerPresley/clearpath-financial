"""A drift_detected re-review: Reaffirm only once the placement's latest check finds the approved copy again."""

import pytest
from django.test import Client

from accounts.models import User
from core.clock import FixedClock
from core.domain import ItemStatus, ReopenReason
from drift import services
from drift.fetcher import FetchError, FetchFailure
from drift.tests.conftest import page_with
from drift.tests.test_services import EDITED, check
from reviews.decisions import reaffirm
from reviews.errors import DriftNotRestored
from reviews.models import Decision, Placement, ReviewItem
from reviews.records import get_item_detail
from reviews.rereview import send_back
from reviews.selectors import DriftRereview

pytestmark = pytest.mark.django_db


@pytest.fixture
def drifted(placement: Placement, clock: FixedClock, enqueued: list[int]) -> ReviewItem:
    services.complete(claim=check(placement, clock), page=page_with(EDITED), clock=clock)
    item = ReviewItem.objects.get(pk=placement.item_id)  # pyrefly: ignore[missing-attribute]
    assert item.reopen_reason == ReopenReason.DRIFT_DETECTED
    return item


def test_reaffirm_is_refused_while_the_page_still_differs(
    drifted: ReviewItem, reviewer: User, clock: FixedClock
) -> None:
    with pytest.raises(DriftNotRestored) as refused:
        reaffirm(actor=reviewer, item_id=drifted.pk, reason="Looks fine", clock=clock)

    assert refused.value.code == "drift_not_restored"
    assert refused.value.message == (
        "The partner page doesn't show the approved copy. Check it again once the partner restores it, or pull it."
    )
    assert ReviewItem.objects.get(pk=drifted.pk).status == ItemStatus.NEEDS_REREVIEW
    assert Decision.objects.filter(item=drifted, lane="reaffirm").count() == 0


def test_reaffirm_is_allowed_once_a_check_finds_the_copy_restored(
    drifted: ReviewItem, placement: Placement, reviewer: User, clock: FixedClock
) -> None:
    services.complete(claim=check(placement, clock), page=page_with(), clock=clock)

    reaffirm(actor=reviewer, item_id=drifted.pk, reason="Partner restored the copy", clock=clock)

    assert ReviewItem.objects.get(pk=drifted.pk).status == ItemStatus.APPROVED


def test_a_failed_check_after_the_restore_refuses_again(
    drifted: ReviewItem, placement: Placement, reviewer: User, clock: FixedClock
) -> None:
    services.complete(claim=check(placement, clock), page=page_with(), clock=clock)
    services.fail(claim=check(placement, clock), error=FetchError(FetchFailure.TIMEOUT), clock=clock)

    with pytest.raises(DriftNotRestored):
        reaffirm(actor=reviewer, item_id=drifted.pk, reason="Looks fine", clock=clock)


def test_a_page_unreachable_three_times_is_not_restored(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    for _ in range(3):
        services.fail(
            claim=check(placement, clock), error=FetchError(FetchFailure.HTTP_ERROR, http_status=404), clock=clock
        )
    item_id = placement.item_id  # pyrefly: ignore[missing-attribute]

    with pytest.raises(DriftNotRestored):
        reaffirm(actor=reviewer, item_id=item_id, reason="Looks fine", clock=clock)
    assert get_item_detail(item_id=item_id, clock=clock).drift_rereview == DriftRereview(
        placement_id=placement.pk, restored=False
    )


def test_item_detail_says_which_placement_and_whether_it_was_restored(
    drifted: ReviewItem, placement: Placement, clock: FixedClock
) -> None:
    assert get_item_detail(item_id=drifted.pk, clock=clock).drift_rereview == DriftRereview(
        placement_id=placement.pk, restored=False
    )

    services.complete(claim=check(placement, clock), page=page_with(), clock=clock)

    assert get_item_detail(item_id=drifted.pk, clock=clock).drift_rereview == DriftRereview(
        placement_id=placement.pk, restored=True
    )


def test_other_rereviews_carry_no_drift_state(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    item_id = placement.item_id  # pyrefly: ignore[missing-attribute]
    assert get_item_detail(item_id=item_id, clock=clock).drift_rereview is None  # approved

    send_back(item_id=item_id, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)

    assert get_item_detail(item_id=item_id, clock=clock).drift_rereview is None
    reaffirm(actor=reviewer, item_id=item_id, reason="Still accurate", clock=clock)  # not gated on drift


def test_the_api_refuses_with_a_typed_conflict(drifted: ReviewItem, reviewer: User) -> None:
    client = Client()
    client.force_login(reviewer)

    response = client.post(
        f"/api/items/{drifted.pk}/reaffirm", {"reason": "Looks fine"}, content_type="application/json"
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "drift_not_restored"
    assert body["details"] == {"placement_id": Placement.objects.get(item=drifted).pk}
