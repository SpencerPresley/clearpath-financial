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
    DecisionLane,
    DecisionOutcome,
    EventType,
    FindingSource,
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


class ItemExpiredPayload(EventPayload):
    """approved -> expired (not live)."""

    reason: ReopenReason
    offer_terms_id: int | None = None
    generated_version_id: int | None = None


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


class LlmCheckSucceededPayload(EventPayload):
    version_id: int
    check_run_id: int
    findings_count: int
    dropped_findings_count: int


class LlmCheckFailedPayload(EventPayload):
    version_id: int
    check_run_id: int
    error: str


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
    EventType.ITEM_WITHDRAWN: ItemWithdrawnPayload,
    EventType.ITEM_NEW_ROUND_STARTED: ItemNewRoundStartedPayload,
    EventType.ITEM_IMPORTED: ItemImportedPayload,
    EventType.VERSION_CREATED: VersionCreatedPayload,
    EventType.CHECKS_COMPLETED: ChecksCompletedPayload,
    EventType.LLM_CHECK_REQUESTED: LlmCheckRequestedPayload,
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
