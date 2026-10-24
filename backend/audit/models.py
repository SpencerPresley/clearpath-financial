"""The append-only event log, which doubles as the transactional outbox (decisions.md "Data")."""

from django.conf import settings
from django.db import models

from core.db import CurrentTransactionId


class Event(models.Model):
    """One action. Written by services in the same transaction as the state it records; never updated or
    deleted (trigger). `payload` is the JSON of the `audit.payloads` model registered for `type`.

    `type` and `entity` have no DB choices on purpose: adding an EventType needs no migration here.
    """

    type = models.CharField(max_length=64)
    entity = models.CharField(max_length=30)
    entity_id = models.BigIntegerField()
    # The item this event belongs to, when there is one: the item's History tab and metrics read by it.
    item = models.ForeignKey(
        "reviews.ReviewItem", null=True, blank=True, on_delete=models.PROTECT, related_name="events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    at = models.DateTimeField()
    from_status = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001  # null = no status change
    to_status = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    payload = models.JSONField()
    # The inserting transaction's id. The dispatcher orders by (txid, id) and only reads events from
    # transactions older than every running one, so an event committed late is never skipped.
    txid = models.BigIntegerField(db_default=CurrentTransactionId())

    class Meta:
        indexes = [
            models.Index(fields=["txid", "id"], name="event_outbox_idx"),
            models.Index(fields=["item", "id"], name="event_item_idx"),
            models.Index(fields=["entity", "entity_id", "id"], name="event_entity_idx"),
            models.Index(fields=["type", "at"], name="event_type_at_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.pk} {self.type}"


class OutboxCursor(models.Model):
    """How far the dispatcher has read, as a (txid, id) position."""

    name = models.CharField(max_length=50, unique=True)
    last_txid = models.BigIntegerField(default=0)
    last_event_id = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.name} @ ({self.last_txid}, {self.last_event_id})"


class ProcessedEvent(models.Model):
    """Receipt that `handler` applied `event`. Written in the handler's transaction, so a replayed delivery
    finds it and does nothing (idempotency keyed by event id and handler name)."""

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="receipts")
    handler = models.CharField(max_length=100)
    processed_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "handler"], name="processed_event_once")]

    def __str__(self) -> str:
        return f"{self.handler} applied {self.pk}"
