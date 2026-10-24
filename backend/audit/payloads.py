"""One payload model per EventType: what each event records beyond who, when, and which entity.

Payloads are the event schema handlers and metrics read, so fields are only added, never renamed. The
completeness test fails if an EventType has no payload model.
"""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.domain import (
    AssignmentMode,
    AttachmentKind,
    CheckStatus,
    DecisionLane,
    DecisionOutcome,
    DriftResult,
    DriftTrigger,
    EventType,
    FindingSource,
    LlmFailureCode,
    PartnerType,
    Product,
    ReopenReason,
    RiskTier,
    Role,
    VersionOrigin,
)


class EventPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FieldChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    before: str | list[str] | bool | None
    after: str | list[str] | bool | None


# --- items ---------------------------------------------------------------------------------------------------


class ItemSubmittedPayload(EventPayload):
    version_id: int
    version_n: int
    round: int
    risk_tier: RiskTier
    content_sha256: str


class ItemResubmittedPayload(EventPayload):
    version_id: int
    version_n: int
    round: int
    previous_version_id: int
    note: str = ""  # the marketer's "what changed", for the reviewer


class ItemAssignedPayload(EventPayload):
    assignee_id: int | None  # None: sent to the unassigned pool
    previous_assignee_id: int | None
    mode: AssignmentMode
    reason: str  # e.g. "Dana: load 4 vs Sam 7"


class ItemReviewStartedPayload(EventPayload):
    reviewer_id: int


class ItemFieldsUpdatedPayload(EventPayload):
    changes: tuple[FieldChange, ...]


class ItemRiskTierOverriddenPayload(EventPayload):
    before: RiskTier
    after: RiskTier


class ItemReopenedPayload(EventPayload):
    """approved -> needs_rereview (live content)."""

    reason: ReopenReason
    offer_terms_id: int | None = None  # the new terms version, for terms_changed
    generated_version_id: int | None = None  # the fast-track v+1, if one was generated
    # The drift check that found the change, for drift_detected. Left out when unset, so other reopen events keep
    # the shape they were recorded with.
    snapshot_id: int | None = Field(default=None, exclude_if=lambda v: v is None)


class ItemExpiredPayload(EventPayload):
    """approved -> expired (not live)."""

    reason: ReopenReason
    offer_terms_id: int | None = None
    generated_version_id: int | None = None


class ApprovalExpiringPayload(EventPayload):
    """The daily sweep's warning, 30 days ahead; one per approving decision."""

    decision_id: int
    expires_at: datetime


class ItemWithdrawnPayload(EventPayload):
    reason: str
    placement_ids: tuple[int, ...]


class ItemNewRoundStartedPayload(EventPayload):
    version_id: int
    version_n: int
    round: int


class LegacyTimeline(BaseModel):
    """The tracker's own dates for an imported row. The event's `occurred_at` is the import time, so metrics
    (time to first review, rounds per item) read these instead. Every field is optional: the tracker is messy,
    and a missing date is recorded as missing rather than guessed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    submitted_at: datetime | None = None
    first_reviewed_at: datetime | None = None
    decided_at: datetime | None = None
    outcome: DecisionOutcome | None = None
    rounds: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        dates = [d for d in (self.submitted_at, self.first_reviewed_at, self.decided_at) if d is not None]
        if dates != sorted(dates):
            raise ValueError("submitted_at, first_reviewed_at, and decided_at must be in order")
        return self


class ItemImportedPayload(EventPayload):
    import_id: int
    legacy_ref: str
    row_number: int
    timeline: LegacyTimeline = LegacyTimeline()


# --- versions, checks, findings ------------------------------------------------------------------------------


class VersionCreatedPayload(EventPayload):
    version_id: int
    version_n: int
    origin: VersionOrigin
    based_on_version_id: int | None


class ChecksCompletedPayload(EventPayload):
    version_id: int
    source: FindingSource
    findings_count: int
    blocking_count: int
    ruleset_key: str


class LlmCheckRequestedPayload(EventPayload):
    version_id: int
    check_run_id: int | None = None
    retry: bool = False  # a reviewer asked to run a failed check again


class LlmCheckStartedPayload(EventPayload):
    version_id: int
    check_run_id: int
    attempt: int  # 1 for the first call; retries after a provider error or unreadable output count up


class LlmCheckRetryScheduledPayload(EventPayload):
    """An attempt ended without a result that retrying can fix; the next one starts after `countdown_s`."""

    version_id: int
    check_run_id: int
    attempt: int  # the attempt that just ended
    error: str
    countdown_s: int


class LlmCheckSucceededPayload(EventPayload):
    """What one AI pre-review cost and produced (spec §6.4: model, tokens, latency, dropped findings)."""

    version_id: int
    check_run_id: int
    findings_count: int
    dropped_findings_count: int
    model: str = ""
    ruleset_key: str = ""
    prompt_version: str = ""
    latency_ms: int = 0
    input_tokens: int = 0  # cached tokens included
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    dropped_by_reason: dict[str, int] = Field(default_factory=dict)
    adjustments_by_kind: dict[str, int] = Field(default_factory=dict)
    attempt: int = 1
    # False: the version was replaced while the call ran. Its findings are stored; the item's status is untouched.
    current: bool = True


class LlmCheckFailedPayload(EventPayload):
    version_id: int
    check_run_id: int
    error: str  # a plain sentence for the reviewer
    code: LlmFailureCode = LlmFailureCode.ERROR
    attempt: int = 1
    current: bool = True


class FindingAcceptedPayload(EventPayload):
    finding_id: int
    version_id: int
    rule_id: str
    note: str = ""


class FindingDismissedPayload(EventPayload):
    finding_id: int
    version_id: int
    rule_id: str
    reason: str
    carried: bool = False


class FindingReopenedPayload(EventPayload):
    finding_id: int
    version_id: int
    rule_id: str


class CommentAddedPayload(EventPayload):
    comment_id: int
    version_id: int
    mention_user_ids: tuple[int, ...] = ()


# --- decisions and placements --------------------------------------------------------------------------------


class DecisionRecordedPayload(EventPayload):
    decision_id: int
    version_id: int
    outcome: DecisionOutcome
    lane: DecisionLane
    reason: str
    expires_at: datetime | None
    terms_version_ids: tuple[int, ...] = ()
    evidence_attachment_ids: tuple[int, ...] = ()
    ruleset_date: date | None = None
    engine_version: str = ""
    ai_review_carried_from_version_id: int | None = None
    llm_override_reason: str = ""


class PlacementRecordedPayload(EventPayload):
    placement_id: int
    version_id: int
    location: str
    first_run: date
    last_run: date | None


class PlacementUpdatedPayload(EventPayload):
    placement_id: int
    changes: tuple[FieldChange, ...]


class TakedownRequestedPayload(EventPayload):
    placement_id: int
    reason: str


class TakedownConfirmedPayload(EventPayload):
    placement_id: int


class DriftCheckRequestedPayload(EventPayload):
    placement_id: int
    snapshot_id: int
    trigger: DriftTrigger


class DriftCheckedPayload(EventPayload):
    placement_id: int
    snapshot_id: int
    status: Literal[CheckStatus.SUCCEEDED, CheckStatus.FAILED]
    result: DriftResult | None = None  # set iff succeeded
    compared_version_id: int | None = None  # the latest approved version the page was compared with
    score: float | None = None
    findings_count: int = 0  # code findings on the whole page
    new_findings_count: int = 0  # ... of rules that don't fire on the approved copy
    error_code: str = ""  # drift.fetcher.FetchFailure, or "stuck" / "error"


class AttachmentAddedPayload(EventPayload):
    attachment_id: int
    kind: AttachmentKind
    sha256: str
    owner_type: Literal["item", "version", "partner", "decision"]
    owner_id: int


# --- terms, partners, users, system --------------------------------------------------------------------------


class TermsPublishedPayload(EventPayload):
    offer_terms_id: int
    product: Product
    version: int
    previous_offer_terms_id: int | None
    affected_item_ids: tuple[int, ...] = ()


class PartnerCreatedPayload(EventPayload):
    partner_id: int
    name: str
    type: PartnerType


class PartnerUpdatedPayload(EventPayload):
    partner_id: int
    changes: tuple[FieldChange, ...]


class UserAvailabilityChangedPayload(EventPayload):
    user_id: int
    is_available: bool


class UserCreatedPayload(EventPayload):
    user_id: int
    email: str
    roles: tuple[Role, ...]


class UserRolesChangedPayload(EventPayload):
    user_id: int
    before: tuple[Role, ...]
    after: tuple[Role, ...]


class UserActiveChangedPayload(EventPayload):
    user_id: int
    is_active: bool


class ImportCommittedPayload(EventPayload):
    import_id: int
    created_count: int
    skipped_count: int


class ExportCreatedPayload(EventPayload):
    export_id: int
    item_count: int


class EmailSentPayload(EventPayload):
    email_id: int
    to: tuple[str, ...]
    subject: str
    approved_by_id: int


class DemoResetPayload(EventPayload):
    seeded_items: int = 0


PAYLOADS: Final[Mapping[EventType, type[EventPayload]]] = {
    EventType.ITEM_SUBMITTED: ItemSubmittedPayload,
    EventType.ITEM_RESUBMITTED: ItemResubmittedPayload,
    EventType.ITEM_ASSIGNED: ItemAssignedPayload,
    EventType.ITEM_REVIEW_STARTED: ItemReviewStartedPayload,
    EventType.ITEM_FIELDS_UPDATED: ItemFieldsUpdatedPayload,
    EventType.ITEM_RISK_TIER_OVERRIDDEN: ItemRiskTierOverriddenPayload,
    EventType.ITEM_REOPENED: ItemReopenedPayload,
    EventType.ITEM_EXPIRED: ItemExpiredPayload,
    EventType.APPROVAL_EXPIRING: ApprovalExpiringPayload,
    EventType.ITEM_WITHDRAWN: ItemWithdrawnPayload,
    EventType.ITEM_NEW_ROUND_STARTED: ItemNewRoundStartedPayload,
    EventType.ITEM_IMPORTED: ItemImportedPayload,
    EventType.VERSION_CREATED: VersionCreatedPayload,
    EventType.CHECKS_COMPLETED: ChecksCompletedPayload,
    EventType.LLM_CHECK_REQUESTED: LlmCheckRequestedPayload,
    EventType.LLM_CHECK_STARTED: LlmCheckStartedPayload,
    EventType.LLM_CHECK_RETRY_SCHEDULED: LlmCheckRetryScheduledPayload,
    EventType.LLM_CHECK_SUCCEEDED: LlmCheckSucceededPayload,
    EventType.LLM_CHECK_FAILED: LlmCheckFailedPayload,
    EventType.FINDING_ACCEPTED: FindingAcceptedPayload,
    EventType.FINDING_DISMISSED: FindingDismissedPayload,
    EventType.FINDING_REOPENED: FindingReopenedPayload,
    EventType.COMMENT_ADDED: CommentAddedPayload,
    EventType.DECISION_RECORDED: DecisionRecordedPayload,
    EventType.PLACEMENT_RECORDED: PlacementRecordedPayload,
    EventType.PLACEMENT_UPDATED: PlacementUpdatedPayload,
    EventType.TAKEDOWN_REQUESTED: TakedownRequestedPayload,
    EventType.TAKEDOWN_CONFIRMED: TakedownConfirmedPayload,
    EventType.DRIFT_CHECK_REQUESTED: DriftCheckRequestedPayload,
    EventType.DRIFT_CHECKED: DriftCheckedPayload,
    EventType.ATTACHMENT_ADDED: AttachmentAddedPayload,
    EventType.TERMS_PUBLISHED: TermsPublishedPayload,
    EventType.PARTNER_CREATED: PartnerCreatedPayload,
    EventType.PARTNER_UPDATED: PartnerUpdatedPayload,
    EventType.USER_AVAILABILITY_CHANGED: UserAvailabilityChangedPayload,
    EventType.USER_CREATED: UserCreatedPayload,
    EventType.USER_ROLES_CHANGED: UserRolesChangedPayload,
    EventType.USER_ACTIVE_CHANGED: UserActiveChangedPayload,
    EventType.IMPORT_COMMITTED: ImportCommittedPayload,
    EventType.EXPORT_CREATED: ExportCreatedPayload,
    EventType.EMAIL_SENT: EmailSentPayload,
    EventType.DEMO_RESET: DemoResetPayload,
}


def parse_payload(event_type: EventType, data: object) -> EventPayload:
    return PAYLOADS[event_type].model_validate(data)
