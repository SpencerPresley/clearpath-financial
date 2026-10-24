"""The inbox renders "Dana Reyes requested changes on CP-42 · Spring email" from these rows, so each row carries
who acted, the item's title, and what the source event says (outcome, assignment mode, comment version)."""

from datetime import UTC, datetime

import pytest
from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from audit.outbox import deliver
from audit.payloads import (
    ApprovalExpiringPayload,
    CommentAddedPayload,
    DecisionRecordedPayload,
    ItemAssignedPayload,
    ItemReopenedPayload,
)
from audit.services import record_event
from core.clock import FixedClock
from core.domain import (
    AssignmentMode,
    DecisionLane,
    DecisionOutcome,
    EntityType,
    EventType,
    NotificationKind,
    ReopenReason,
)
from notifications.models import Notification
from notifications.selectors import (
    AssignmentDetail,
    DecisionDetail,
    ExpiryWarningDetail,
    MentionDetail,
    NotificationRow,
    RereviewDetail,
    list_notifications,
)
from reviews.models import ReviewItem
from reviews.selectors import PartyRef
from reviews.tests.factories import make_item, make_version


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


def _only_row(user: User) -> NotificationRow:
    (row,) = list_notifications(user=user).rows
    return row


@pytest.mark.django_db
def test_decision_row_carries_actor_title_and_outcome(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer, title="Fall personal loan promo")
    payload = DecisionRecordedPayload(
        decision_id=1,
        version_id=1,
        outcome=DecisionOutcome.CHANGES_REQUESTED,
        lane=DecisionLane.STANDARD,
        reason="Add the APR range",
        expires_at=None,
    )
    deliver(
        event_id=_emit(item, reviewer, EventType.DECISION_RECORDED, payload, clock),
        handler_name="notifications.decision",
    )

    row = _only_row(marketer)

    assert row.kind is NotificationKind.DECISION
    assert row.actor == PartyRef(id=reviewer.pk, name="Riley Reviewer")
    assert (row.item_id, row.item_key, row.item_title) == (item.pk, item.key, "Fall personal loan promo")
    assert row.detail == DecisionDetail(outcome=DecisionOutcome.CHANGES_REQUESTED)


@pytest.mark.django_db
def test_mention_row_carries_the_comment_and_its_version_number(
    marketer: User, reviewer: User, clock: FixedClock
) -> None:
    item = make_item(marketer)
    make_version(item, "v1 copy", n=1)
    v2 = make_version(item, "v2 copy", n=2)
    payload = CommentAddedPayload(comment_id=77, version_id=v2.pk, mention_user_ids=(marketer.pk,))
    deliver(
        event_id=_emit(item, reviewer, EventType.COMMENT_ADDED, payload, clock), handler_name="notifications.mention"
    )

    assert _only_row(marketer).detail == MentionDetail(comment_id=77, version_n=2)


@pytest.mark.django_db
def test_assignment_rereview_and_expiry_rows_carry_their_detail(
    marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = make_item(marketer, assignee=reviewer)
    assigned = ItemAssignedPayload(
        assignee_id=reviewer.pk, previous_assignee_id=None, mode=AssignmentMode.MANUAL, reason="lead's call"
    )
    deliver(
        event_id=_emit(item, lead, EventType.ITEM_ASSIGNED, assigned, clock), handler_name="notifications.assignment"
    )
    reopened = ItemReopenedPayload(reason=ReopenReason.TERMS_CHANGED)
    deliver(event_id=_emit(item, lead, EventType.ITEM_REOPENED, reopened, clock), handler_name="notifications.rereview")
    expires = datetime(2026, 11, 23, tzinfo=UTC)
    expiring = ApprovalExpiringPayload(decision_id=1, expires_at=expires)
    deliver(
        event_id=_emit(item, None, EventType.APPROVAL_EXPIRING, expiring, clock),
        handler_name="notifications.expiry_warning",
    )

    by_kind = {row.kind: row for row in list_notifications(user=reviewer).rows}

    assert by_kind[NotificationKind.ASSIGNMENT].detail == AssignmentDetail(mode=AssignmentMode.MANUAL)
    assert by_kind[NotificationKind.ASSIGNMENT].actor == PartyRef(id=lead.pk, name="Lee Lead")
    assert by_kind[NotificationKind.REREVIEW].detail == RereviewDetail(reason=ReopenReason.TERMS_CHANGED)
    assert by_kind[NotificationKind.EXPIRY_WARNING].detail == ExpiryWarningDetail(expires_at=expires)
    assert by_kind[NotificationKind.EXPIRY_WARNING].actor is None  # the daily sweep


@pytest.mark.django_db
def test_row_without_an_event_falls_back_to_its_message(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer, title="Card page")
    Notification.objects.create(
        user=marketer,
        kind=NotificationKind.DECISION,
        item=item,
        message="CP-1 Card page: approved",
        created_at=clock.now(),
    )

    row = _only_row(marketer)

    assert (row.actor, row.detail, row.item_title) == (None, None, "Card page")
    assert row.message == "CP-1 Card page: approved"


@pytest.mark.django_db
def test_api_serializes_the_detail_with_its_kind(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    version = make_version(item, "copy", n=1)
    payload = CommentAddedPayload(comment_id=5, version_id=version.pk, mention_user_ids=(marketer.pk,))
    deliver(
        event_id=_emit(item, reviewer, EventType.COMMENT_ADDED, payload, clock), handler_name="notifications.mention"
    )
    client = Client()
    client.force_login(marketer)

    (row,) = client.get("/api/notifications").json()["rows"]

    assert row["actor"] == {"id": reviewer.pk, "name": "Riley Reviewer"}
    assert row["item_title"] == item.title
    assert row["detail"] == {"kind": "mention", "comment_id": 5, "version_n": 1}


@pytest.mark.django_db
def test_listing_query_count_does_not_grow_with_rows(marketer: User, reviewer: User, clock: FixedClock) -> None:
    def grow(n: int) -> None:
        for _ in range(n):
            item = make_item(marketer)
            version = make_version(item, "copy", n=1)
            mention = CommentAddedPayload(comment_id=1, version_id=version.pk, mention_user_ids=(marketer.pk,))
            deliver(
                event_id=_emit(item, reviewer, EventType.COMMENT_ADDED, mention, clock),
                handler_name="notifications.mention",
            )
            decision = DecisionRecordedPayload(
                decision_id=1,
                version_id=version.pk,
                outcome=DecisionOutcome.APPROVED,
                lane=DecisionLane.STANDARD,
                reason="ok",
                expires_at=None,
            )
            deliver(
                event_id=_emit(item, reviewer, EventType.DECISION_RECORDED, decision, clock),
                handler_name="notifications.decision",
            )
            Notification.objects.create(
                user=marketer, kind=NotificationKind.DECISION, item=item, message="legacy", created_at=clock.now()
            )

    def queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            page = list_notifications(user=marketer)
        assert page.rows
        return len(ctx.captured_queries)

    grow(1)
    small = queries()
    grow(4)

    assert queries() == small
