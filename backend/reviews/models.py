"""Review items, their immutable versions, and everything a decision is recorded against.

Persistence only: state changes go through `reviews.services`. Invariants are enforced here as Postgres
constraints and triggers (spec §6.1, "enforce invariants in the database as the last line of defense").
"""

import hashlib
from functools import reduce
from operator import or_
from typing import Final

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Cast, Length, Trim, Upper
from django.db.models.lookups import GreaterThan

from core.domain import (
    PARTNER_CHANNELS,
    CheckStatus,
    DecisionLane,
    DecisionOutcome,
    ExpiryRule,
    ItemStatus,
    RiskTier,
    TakedownState,
    VersionOrigin,
)

# Statuses that sit in a reviewer's queue (the partial queue indexes cover exactly these).
QUEUE_STATUSES: Final = (ItemStatus.SUBMITTED.value, ItemStatus.IN_REVIEW.value, ItemStatus.NEEDS_REREVIEW.value)
APPROVED_OUTCOMES: Final = (DecisionOutcome.APPROVED.value, DecisionOutcome.APPROVED_WITH_EDITS.value)

_SHA256_HEX = r"^[0-9a-f]{64}$"


def _non_blank(field: str) -> GreaterThan:
    return GreaterThan(Length(Trim(field)), 0)


def _span_valid(prefix: str = "span") -> Q:
    start, end = f"{prefix}_start", f"{prefix}_end"
    both_null = Q(**{f"{start}__isnull": True, f"{end}__isnull": True})
    ordered = Q(**{f"{start}__gte": 0, f"{end}__gt": F(start)})
    return both_null | ordered


def _exactly_one_set(*fields: str) -> Q:
    def only(field: str) -> Q:
        q = Q(**{f"{field}__isnull": False})
        for other in fields:
            if other != field:
                q &= Q(**{f"{other}__isnull": True})
        return q

    return reduce(or_, (only(f) for f in fields))


class ReviewItem(models.Model):
    """One piece of marketing content moving through review. Shown as `CP-<id>`."""

    title = models.CharField(max_length=300)
    product = models.CharField(max_length=30)
    channel = models.CharField(max_length=30)
    partner = models.ForeignKey(
        "partners.Partner", null=True, blank=True, on_delete=models.PROTECT, related_name="items"
    )
    markets = ArrayField(models.CharField(max_length=20), default=list)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="owned_items"
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_items"
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=30, default=ItemStatus.DRAFT.value)
    round = models.PositiveIntegerField(default=1)
    # Derived at intake (spec §4.2 ruling 5); reviewers and leads may override, which records an event.
    risk_tier = models.CharField(max_length=10)
    risk_tier_overridden = models.BooleanField(default=False)
    # A prescreened firm offer (FCRA): drives risk tier and the "pre-approved" rule's evidence requirement.
    is_prescreen = models.BooleanField(default=False)
    reopen_reason = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001  # null = not reopened
    llm_check_status = models.CharField(max_length=20, default=CheckStatus.PENDING.value)

    # Legacy imports are metadata-only (spec §4.2 ruling 7): no versions, excluded from sweeps and fan-out.
    is_legacy = models.BooleanField(default=False)
    legacy_ref = models.CharField(max_length=64, null=True, blank=True, unique=True)  # the tracker's Request ID
    legacy_submitter = models.CharField(max_length=200, blank=True)
    legacy_reviewer = models.CharField(max_length=200, blank=True)
    legacy_history = models.TextField(blank=True)  # the tracker's multi-round comments cell, verbatim

    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    notes = models.TextField(blank=True)
    planned_first_run = models.DateField(null=True, blank=True)
    planned_last_run = models.DateField(null=True, blank=True)
    source_url = models.URLField(max_length=2000, blank=True)

    current_version = models.ForeignKey(
        "reviews.Version", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Denormalized: maintained by the services that create and triage findings (queue speed, decisions.md).
    open_findings_count = models.PositiveIntegerField(default=0)

    submitted_at = models.DateTimeField()  # latest (re)submission by the marketer
    # When the item last entered the reviewers' queue: submission, resubmission, a new round, or a reopen
    # (re-review). The queue's Age, "Waiting >3 days", and age order measure from it (walkthrough S4): a re-review
    # opened a minute ago isn't 8 weeks old. Maintained by `reviews.transitions.apply_transition` and intake.
    queue_entered_at = models.DateTimeField()
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_expires_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    # Queue order (spec §4.3 Review): re-reviews of live content first, then risk tier; age breaks ties via
    # queue_entered_at in the index. A re-review is a queued item with a reopen_reason, so it keeps its priority
    # when a reviewer opens it (in_review) and through a changes_requested -> submitted loop. An expired item
    # is not queued. Contract for E: clear reopen_reason when the re-review resolves (approve, reaffirm,
    # withdraw) and when a marketer starts a new round from expired.
    queue_priority = models.GeneratedField(
        expression=Case(
            When(Q(reopen_reason__isnull=False) & Q(status__in=QUEUE_STATUSES), then=Value(0)),
            default=Value(10),
        )
        + Case(
            When(risk_tier=RiskTier.HIGH.value, then=Value(0)),
            When(risk_tier=RiskTier.MEDIUM.value, then=Value(1)),
            default=Value(2),
        ),
        output_field=models.PositiveSmallIntegerField(),
        db_persist=True,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(is_legacy=True)
                | ~Q(channel__in=[c.value for c in PARTNER_CHANNELS])
                | Q(partner__isnull=False),
                name="item_partner_channel_has_partner",
            ),
            models.CheckConstraint(
                condition=Q(is_legacy=True) | Q(owner__isnull=False), name="item_has_owner_unless_legacy"
            ),
            models.CheckConstraint(
                condition=Q(is_legacy=True) | Q(markets__len__gte=1), name="item_has_market_unless_legacy"
            ),
            models.CheckConstraint(condition=Q(round__gte=1), name="item_round_positive"),
            # The queue's re-review priority keys on reopen_reason; needs_rereview always carries one.
            models.CheckConstraint(
                condition=~Q(status=ItemStatus.NEEDS_REREVIEW.value) | Q(reopen_reason__isnull=False),
                name="item_rereview_has_reason",
            ),
            models.CheckConstraint(
                condition=Q(planned_last_run__isnull=True)
                | Q(planned_first_run__isnull=True)
                | Q(planned_last_run__gte=F("planned_first_run")),
                name="item_planned_run_ordered",
            ),
            models.CheckConstraint(
                condition=Q(is_legacy=False) | Q(legacy_ref__isnull=False), name="item_legacy_has_ref"
            ),
        ]
        indexes = [
            models.Index(
                fields=["queue_priority", "queue_entered_at", "id"],
                condition=Q(status__in=QUEUE_STATUSES),
                name="item_queue_idx",
            ),
            models.Index(
                fields=["assignee", "queue_priority", "queue_entered_at", "id"],
                condition=Q(status__in=QUEUE_STATUSES),
                name="item_assignee_queue_idx",
            ),
            # Matches Django's icontains SQL, UPPER(col::text) LIKE UPPER(%s), so the planner can use it.
            GinIndex(
                OpClass(Upper(Cast("title", models.TextField())), name="gin_trgm_ops"), name="item_title_trgm_idx"
            ),
            GinIndex(fields=["tags"], name="item_tags_gin_idx"),
            models.Index(fields=["owner", "-updated_at"], name="item_owner_idx"),
            models.Index(fields=["partner", "-submitted_at"], name="item_partner_idx"),
            models.Index(
                fields=["-approved_at", "id"], condition=Q(status=ItemStatus.APPROVED.value), name="item_approved_idx"
            ),
            models.Index(fields=["status", "-updated_at"], name="item_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.key} {self.title}"

    @property
    def key(self) -> str:
        return f"CP-{self.pk}"


class Version(models.Model):
    """The exact content reviewed in one round. Immutable (trigger): edits create v+1."""

    item = models.ForeignKey(ReviewItem, on_delete=models.PROTECT, related_name="versions")
    n = models.PositiveIntegerField()
    content_text = models.TextField()
    content_sha256 = models.CharField(max_length=64)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    origin = models.CharField(max_length=20, default=VersionOrigin.SUBMISSION.value)
    # Fast-track and reviewer-edit versions record what they were derived from ("AI review carried from vN").
    based_on = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()
    search_vector = models.GeneratedField(
        expression=SearchVector("content_text", config="english"),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "n"], name="version_unique_n_per_item"),
            # Target of the composite FKs (reviews 0006) that keep a decision's, placement's, and item's
            # version on the same item.
            models.UniqueConstraint(fields=["id", "item"], name="version_id_item_unique"),
            models.CheckConstraint(condition=Q(n__gte=1), name="version_n_positive"),
            models.CheckConstraint(condition=Q(content_sha256__regex=_SHA256_HEX), name="version_sha256_hex"),
        ]
        indexes = [
            GinIndex(fields=["search_vector"], name="version_search_idx"),
            GinIndex(OpClass(Upper("content_text"), name="gin_trgm_ops"), name="version_content_trgm_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.item_id} v{self.n}"

    @staticmethod
    def hash_content(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


class Comment(models.Model):
    version = models.ForeignKey(Version, on_delete=models.PROTECT, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    span_start = models.PositiveIntegerField(null=True, blank=True)
    span_end = models.PositiveIntegerField(null=True, blank=True)
    mentions = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="mentioned_in")
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=_span_valid(), name="comment_span_valid"),
            models.CheckConstraint(condition=_non_blank("body"), name="comment_body_required"),
        ]
        indexes = [models.Index(fields=["version", "created_at"], name="comment_version_idx")]

    def __str__(self) -> str:
        return f"Comment {self.pk} on {self.version_id}"


class Decision(models.Model):
    """What a reviewer decided and exactly what it was decided against. Immutable (trigger)."""

    item = models.ForeignKey(ReviewItem, on_delete=models.PROTECT, related_name="decisions")
    version = models.ForeignKey(Version, on_delete=models.PROTECT, related_name="decisions")
    outcome = models.CharField(max_length=30)
    lane = models.CharField(max_length=20, default=DecisionLane.STANDARD.value)
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.TextField()
    ruleset_date = models.DateField()
    # The rules engine's behavior version (checks.engine.ENGINE_VERSION) the findings were produced with; "" for
    # decisions recorded before it was captured.
    engine_version = models.CharField(max_length=40, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    # Approving with a failed AI check needs a recorded reason (spec §4.2 ruling 3).
    llm_override_reason = models.TextField(blank=True)
    # Fast-track versions skip the AI check; the decision records whose AI review it relied on (ruling 4).
    ai_review_carried_from = models.ForeignKey(
        Version, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    terms_versions = models.ManyToManyField(
        "terms.OfferTerms", through="DecisionTermsVersion", related_name="decisions", blank=True
    )
    decided_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=_non_blank("reason"), name="decision_reason_required"),
            models.CheckConstraint(
                condition=~Q(outcome__in=APPROVED_OUTCOMES) | Q(expires_at__isnull=False),
                name="decision_approval_has_expiry",
            ),
        ]
        indexes = [models.Index(fields=["item", "-decided_at"], name="decision_item_idx")]

    def __str__(self) -> str:
        return f"{self.outcome} {self.version_id}"


class DecisionTermsVersion(models.Model):
    """An offer-terms version the approved copy quotes. Immutable (trigger)."""

    decision = models.ForeignKey(Decision, on_delete=models.PROTECT, related_name="terms_links")
    offer_terms = models.ForeignKey("terms.OfferTerms", on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["decision", "offer_terms"], name="decision_terms_unique")]

    def __str__(self) -> str:
        return f"{self.decision_id} quotes {self.offer_terms.pk}"


class Attachment(models.Model):
    """Supporting evidence. Owned by exactly one of item, version, partner, or decision. Immutable (trigger):
    "replace" adds a row."""

    item = models.ForeignKey(ReviewItem, null=True, blank=True, on_delete=models.PROTECT, related_name="attachments")
    version = models.ForeignKey(Version, null=True, blank=True, on_delete=models.PROTECT, related_name="attachments")
    partner = models.ForeignKey(
        "partners.Partner", null=True, blank=True, on_delete=models.PROTECT, related_name="attachments"
    )
    decision = models.ForeignKey(Decision, null=True, blank=True, on_delete=models.PROTECT, related_name="attachments")
    kind = models.CharField(max_length=30)
    file = models.FileField(upload_to="attachments/%Y/%m/", max_length=500)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=150)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=_exactly_one_set("item", "version", "partner", "decision"), name="attachment_one_owner"
            ),
            models.CheckConstraint(condition=Q(sha256__regex=_SHA256_HEX), name="attachment_sha256_hex"),
        ]
        indexes = [models.Index(fields=["sha256"], name="attachment_sha256_idx")]

    def __str__(self) -> str:
        return self.original_name


class DecisionEvidence(models.Model):
    """Evidence a decision relied on. `sha256` is a deliberate snapshot of the attachment's hash at decision
    time, so the record stands on its own in the evidence pack. Immutable (trigger)."""

    decision = models.ForeignKey(Decision, on_delete=models.PROTECT, related_name="evidence")
    attachment = models.ForeignKey(Attachment, on_delete=models.PROTECT, related_name="+")
    sha256 = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["decision", "attachment"], name="decision_evidence_unique"),
            models.CheckConstraint(condition=Q(sha256__regex=_SHA256_HEX), name="decision_evidence_sha256_hex"),
        ]

    def __str__(self) -> str:
        return f"{self.decision_id} relied on {self.attachment_id}"


class Placement(models.Model):
    """Where an approved version runs, and when (spec §4.2 ruling 2)."""

    item = models.ForeignKey(ReviewItem, on_delete=models.PROTECT, related_name="placements")
    approved_version = models.ForeignKey(Version, on_delete=models.PROTECT, related_name="placements")
    location = models.CharField(max_length=300)
    url = models.URLField(max_length=2000, blank=True)
    first_run = models.DateField()
    last_run = models.DateField(null=True, blank=True)  # null: open-ended
    monitored = models.BooleanField(default=False)  # drift monitor (stretch)
    takedown_state = models.CharField(max_length=20, null=True, blank=True)  # noqa: DJ001  # null = no takedown
    takedown_requested_at = models.DateTimeField(null=True, blank=True)
    takedown_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(last_run__isnull=True) | Q(last_run__gte=F("first_run")), name="placement_run_ordered"
            ),
            models.CheckConstraint(
                condition=Q(takedown_state__isnull=True)
                | (Q(takedown_state=TakedownState.REQUESTED.value) & Q(takedown_requested_at__isnull=False))
                | (Q(takedown_state=TakedownState.CONFIRMED.value) & Q(takedown_confirmed_at__isnull=False)),
                name="placement_takedown_timestamped",
            ),
        ]
        indexes = [models.Index(fields=["item", "first_run"], name="placement_item_idx")]

    def __str__(self) -> str:
        return f"{self.location} ({self.item_id})"


class Snapshot(models.Model):
    """One drift check of a monitored placement's page (drift monitor; written only by `drift.services`).

    pending -> running -> succeeded (with a result) | failed (with an error code). A fetch failure is never a
    result: only a page that was actually read can be unchanged, modified, or missing.
    """

    placement = models.ForeignKey(Placement, on_delete=models.PROTECT, related_name="snapshots")
    status = models.CharField(max_length=20, default=CheckStatus.PENDING.value)
    trigger = models.CharField(max_length=20)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    requested_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    url = models.URLField(max_length=2000)  # the placement's URL when the check was requested
    final_url = models.URLField(max_length=2000, blank=True)  # after redirects
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    title = models.CharField(max_length=500, blank=True)
    text = models.TextField(blank=True)  # visible page text
    content_sha256 = models.CharField(max_length=64, blank=True)
    compared_version = models.ForeignKey(
        Version, null=True, blank=True, on_delete=models.PROTECT, related_name="drift_snapshots"
    )
    result = models.CharField(max_length=20, null=True, blank=True)  # noqa: DJ001  # null until succeeded
    score = models.FloatField(null=True, blank=True)
    matched_text = models.TextField(blank=True)
    diff = models.JSONField(default=list, blank=True)  # [{op, text}]: approved copy -> page region
    findings = models.JSONField(default=list, blank=True)  # code findings on the page text, see drift.services
    error_code = models.CharField(max_length=40, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    reopen_event = models.ForeignKey("audit.Event", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        indexes = [models.Index(fields=["placement", "-requested_at"], name="snapshot_placement_idx")]
        constraints = [
            # Double-clicking "Check now" or a sweep racing it can't start two checks of one page.
            models.UniqueConstraint(
                fields=["placement"],
                condition=Q(status__in=[CheckStatus.PENDING.value, CheckStatus.RUNNING.value]),
                name="snapshot_one_in_flight",
            ),
            models.CheckConstraint(
                condition=(Q(status=CheckStatus.SUCCEEDED.value) & Q(result__isnull=False))
                | (~Q(status=CheckStatus.SUCCEEDED.value) & Q(result__isnull=True)),
                name="snapshot_result_iff_succeeded",
            ),
            models.CheckConstraint(
                condition=~Q(status=CheckStatus.FAILED.value) | ~Q(error_code=""),
                name="snapshot_failure_has_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.placement_id} @ {self.requested_at:%Y-%m-%d} {self.status}"


class ExpiryPolicy(models.Model):
    """How long an approval lasts per channel; company policy, editable (decisions.md "Approval expiry")."""

    channel = models.CharField(max_length=30, unique=True)
    rule = models.CharField(max_length=20)
    months = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "expiry policies"
        constraints = [
            models.CheckConstraint(
                condition=(Q(rule=ExpiryRule.FIXED_MONTHS.value) & Q(months__gte=1))
                | (Q(rule=ExpiryRule.SEND_WINDOW.value) & Q(months__isnull=True)),
                name="expiry_policy_months_iff_fixed",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.channel}: {self.rule} {self.months or ''}".strip()


class SavedView(models.Model):
    """A user's saved queue view. `filters` is an `ItemFilter` serialized as JSON."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_views")
    name = models.CharField(max_length=100)
    filters = models.JSONField(default=dict)
    sort = models.CharField(max_length=20, default="queue")
    columns = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="saved_view_unique_name")]

    def __str__(self) -> str:
        return self.name
