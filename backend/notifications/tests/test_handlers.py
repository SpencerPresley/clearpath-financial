"""In-app notifications come from outbox handlers, so replays must not double-notify."""

import pytest
from django.db import transaction

from accounts.models import User
from audit.outbox import REGISTRY, Delivery, deliver
from audit.payloads import (
    CommentAddedPayload,
    DecisionRecordedPayload,
    ItemAssignedPayload,
    ItemReopenedPayload,
    PageFindingsFlaggedPayload,
)
from audit.services import record_event
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import (
    AssignmentMode,
    DecisionLane,
    DecisionOutcome,
    EntityType,
    EventType,
    NotificationKind,
    ReopenReason,
    Role,
)
from notifications.models import Notification
from reviews.models import ReviewItem
from reviews.tests.factories import make_item


def _emit(item: ReviewItem, actor: User | None, event_type: EventType, payload: object, clock: FixedClock) -> int:
    with transaction.atomic():
        return record_event(
            type=event_type,
            entity=EntityType.ITEM,
            entity_id=item.pk,
            item_id=item.pk,
            payload=payload,  # pyrefly: ignore[bad-argument-type]
            actor=actor,
            at=clock.now(),
        ).pk


@pytest.mark.django_db
def test_assignment_notifies_assignee_once_under_replay(
    marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = make_item(marketer, title="Spring email")
    payload = ItemAssignedPayload(
        assignee_id=reviewer.pk, previous_assignee_id=None, mode=AssignmentMode.MANUAL, reason="lead's call"
    )
    event_id = _emit(item, lead, EventType.ITEM_ASSIGNED, payload, clock)

    outcomes = [deliver(event_id=event_id, handler_name="notifications.assignment") for _ in range(3)]

    assert outcomes == [Delivery.APPLIED, Delivery.DUPLICATE, Delivery.DUPLICATE]
    notification = Notification.objects.get(user=reviewer)
    assert notification.kind == NotificationKind.ASSIGNMENT
    assert notification.item_id == item.pk  # pyrefly: ignore[missing-attribute]
    assert notification.message == f"{item.key} Spring email was assigned to you"
    assert notification.created_at == clock.now()


@pytest.mark.django_db
def test_pool_assignment_notifies_the_active_leads(
    marketer: User, reviewer: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    # decisions.md "Reviewer assignment" rule 3: nobody eligible -> unassigned pool, lead notified.
    lead = user_factory(roles=[Role.LEAD])
    away = user_factory(roles=[Role.LEAD])
    User.objects.filter(pk=away.pk).update(is_active=False)
    item = make_item(marketer, title="Spring email")
    payload = ItemAssignedPayload(
        assignee_id=None, previous_assignee_id=None, mode=AssignmentMode.POOL, reason="nobody available"
    )
    event_id = _emit(item, None, EventType.ITEM_ASSIGNED, payload, clock)

    deliver(event_id=event_id, handler_name="notifications.assignment")

    assert list(Notification.objects.values_list("user_id", "kind", "message")) == [
        (lead.pk, NotificationKind.ASSIGNMENT, f"{item.key} Spring email is in the unassigned pool")
    ]


@pytest.mark.django_db
def test_manual_unassign_notifies_nobody(marketer: User, lead: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    payload = ItemAssignedPayload(
        assignee_id=None, previous_assignee_id=None, mode=AssignmentMode.MANUAL, reason="unassigned"
    )
    event_id = _emit(item, lead, EventType.ITEM_ASSIGNED, payload, clock)

    deliver(event_id=event_id, handler_name="notifications.assignment")

    assert not Notification.objects.exists()


@pytest.mark.django_db
def test_sticky_assignment_tells_the_reviewer_it_is_back(marketer: User, reviewer: User, clock: FixedClock) -> None:
    # Resubmissions and re-reviews return to the previous reviewer (rule 1) via a sticky ITEM_ASSIGNED, which
    # is how "the assignee is notified on resubmit" happens without a second handler double-notifying.
    item = make_item(marketer, title="Spring email")
    payload = ItemAssignedPayload(
        assignee_id=reviewer.pk,
        previous_assignee_id=reviewer.pk,
        mode=AssignmentMode.STICKY,
        reason="previous reviewer",
    )
    event_id = _emit(item, marketer, EventType.ITEM_ASSIGNED, payload, clock)

    deliver(event_id=event_id, handler_name="notifications.assignment")

    assert Notification.objects.get(user=reviewer).message == f"{item.key} Spring email is back for your review"


@pytest.mark.django_db
def test_mentions_notify_each_mentioned_user_but_not_the_author(
    marketer: User, reviewer: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    other = user_factory(roles=[Role.LEAD])
    item = make_item(marketer)
    payload = CommentAddedPayload(comment_id=1, version_id=1, mention_user_ids=(marketer.pk, other.pk, reviewer.pk))
    event_id = _emit(item, reviewer, EventType.COMMENT_ADDED, payload, clock)

    deliver(event_id=event_id, handler_name="notifications.mention")

    assert set(Notification.objects.values_list("user_id", flat=True)) == {marketer.pk, other.pk}
    assert set(Notification.objects.values_list("kind", flat=True)) == {NotificationKind.MENTION}


@pytest.mark.django_db
def test_decision_notifies_the_submitter(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer, title="Card page")
    payload = DecisionRecordedPayload(
        decision_id=1,
        version_id=1,
        outcome=DecisionOutcome.CHANGES_REQUESTED,
        lane=DecisionLane.STANDARD,
        reason="Add APR",
        expires_at=None,
    )
    event_id = _emit(item, reviewer, EventType.DECISION_RECORDED, payload, clock)

    deliver(event_id=event_id, handler_name="notifications.decision")

    notification = Notification.objects.get()
    assert notification.user_id == marketer.pk  # pyrefly: ignore[missing-attribute]
    assert notification.message == f"{item.key} Card page: changes requested"


@pytest.mark.django_db
def test_rereview_notifies_owner_and_assignee(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer, assignee=reviewer)
    event_id = _emit(item, None, EventType.ITEM_REOPENED, ItemReopenedPayload(reason=ReopenReason.TERMS_CHANGED), clock)

    deliver(event_id=event_id, handler_name="notifications.rereview")

    assert set(Notification.objects.values_list("user_id", flat=True)) == {marketer.pk, reviewer.pk}


@pytest.mark.django_db
def test_new_blocking_page_findings_notify_the_assignee_and_active_leads(
    marketer: User, reviewer: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    lead = user_factory(roles=[Role.LEAD])
    away = user_factory(roles=[Role.LEAD])
    User.objects.filter(pk=away.pk).update(is_active=False)
    item = make_item(marketer, assignee=reviewer)
    payload = PageFindingsFlaggedPayload(placement_id=7, snapshot_id=9, rule_ids=["claims.guaranteed"])
    event_id = _emit(item, None, EventType.PAGE_FINDINGS_FLAGGED, payload, clock)

    outcomes = [deliver(event_id=event_id, handler_name="notifications.page_findings") for _ in range(2)]

    assert outcomes == [Delivery.APPLIED, Delivery.DUPLICATE]
    rows = set(Notification.objects.values_list("user_id", "kind", "message"))
    message = f"New blocking findings on a partner page that carries {item.key}"
    assert rows == {
        (reviewer.pk, NotificationKind.PAGE_FINDINGS, message),
        (lead.pk, NotificationKind.PAGE_FINDINGS, message),
    }


def test_notification_handlers_are_registered() -> None:
    names = {spec.name for spec in REGISTRY.all()}

    assert {
        "notifications.assignment",
        "notifications.mention",
        "notifications.decision",
        "notifications.rereview",
        "notifications.page_findings",
    } <= names
