"""Outbox handlers that turn events into in-app notifications (assignment, decision, re-review, mention)."""

from collections.abc import Iterable

from accounts.models import User
from audit.outbox import EventRecord, handles
from audit.payloads import (
    ApprovalExpiringPayload,
    CommentAddedPayload,
    DecisionRecordedPayload,
    ItemAssignedPayload,
)
from core.domain import AssignmentMode, DecisionOutcome, EventType, NotificationKind, Role
from notifications.models import Notification
from reviews.models import ReviewItem

_OUTCOME_WORDS = {
    DecisionOutcome.APPROVED: "approved",
    DecisionOutcome.APPROVED_WITH_EDITS: "approved with edits",
    DecisionOutcome.CHANGES_REQUESTED: "changes requested",
    DecisionOutcome.REJECTED: "rejected",
}


def _notify(event: EventRecord, kind: NotificationKind, user_ids: Iterable[int | None], message: str) -> None:
    recipients = {uid for uid in user_ids if uid is not None and uid != event.actor_id}
    Notification.objects.bulk_create(
        [
            Notification(
                user_id=uid, kind=kind, item_id=event.item_id, event_id=event.id, message=message, created_at=event.at
            )
            for uid in sorted(recipients)
        ],
        ignore_conflicts=True,
    )


def _item(event: EventRecord) -> ReviewItem:
    return ReviewItem.objects.only("id", "title", "owner_id", "assignee_id").get(pk=event.item_id)


@handles(EventType.ITEM_ASSIGNED, name="notifications.assignment")
def notify_assignee(event: EventRecord) -> None:
    """The new assignee; for a pool assignment, the active leads (decisions.md "Reviewer assignment" rule 3).

    A resubmission or re-review records a sticky assignment back to the previous reviewer (rule 1), so this
    is also how that reviewer hears the item is back. A manual unassign notifies nobody.
    """
    payload = event.payload
    assert isinstance(payload, ItemAssignedPayload)  # noqa: S101  # guaranteed by the registry
    if payload.assignee_id is None:
        if payload.mode is not AssignmentMode.POOL:
            return
        item = _item(event)
        leads = User.objects.filter(is_active=True, roles__contains=[Role.LEAD.value]).values_list("pk", flat=True)
        _notify(event, NotificationKind.ASSIGNMENT, leads, f"{item.key} {item.title} is in the unassigned pool")
        return
    item = _item(event)
    if payload.mode is AssignmentMode.STICKY:
        message = f"{item.key} {item.title} is back for your review"
    else:
        message = f"{item.key} {item.title} was assigned to you"
    _notify(event, NotificationKind.ASSIGNMENT, [payload.assignee_id], message)


@handles(EventType.COMMENT_ADDED, name="notifications.mention")
def notify_mentions(event: EventRecord) -> None:
    payload = event.payload
    assert isinstance(payload, CommentAddedPayload)  # noqa: S101
    if not payload.mention_user_ids:
        return
    item = _item(event)
    _notify(event, NotificationKind.MENTION, payload.mention_user_ids, f"{item.key} {item.title}: you were mentioned")


@handles(EventType.DECISION_RECORDED, name="notifications.decision")
def notify_submitter_of_decision(event: EventRecord) -> None:
    payload = event.payload
    assert isinstance(payload, DecisionRecordedPayload)  # noqa: S101
    item = _item(event)
    _notify(
        event,
        NotificationKind.DECISION,
        [item.owner_id],  # pyrefly: ignore[missing-attribute]
        f"{item.key} {item.title}: {_OUTCOME_WORDS[payload.outcome]}",
    )


@handles(EventType.APPROVAL_EXPIRING, name="notifications.expiry_warning")
def notify_expiry_warning(event: EventRecord) -> None:
    """30 days before an approval lapses: the submitter (to plan a refresh) and the reviewer."""
    payload = event.payload
    assert isinstance(payload, ApprovalExpiringPayload)  # noqa: S101
    item = _item(event)
    _notify(
        event,
        NotificationKind.EXPIRY_WARNING,
        [item.owner_id, item.assignee_id],  # pyrefly: ignore[missing-attribute]
        f"{item.key} {item.title}: approval expires {payload.expires_at:%Y-%m-%d}",
    )


@handles(EventType.ITEM_REOPENED, name="notifications.rereview")
def notify_rereview(event: EventRecord) -> None:
    item = _item(event)
    _notify(
        event,
        NotificationKind.REREVIEW,
        [item.owner_id, item.assignee_id],  # pyrefly: ignore[missing-attribute]
        f"{item.key} {item.title} needs re-review",
    )
