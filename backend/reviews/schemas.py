"""API schemas for items, versions, comments, attachments, placements, decisions, saved views, and library.

Names are global in the generated client (one `model/` directory), so every class ends in In/Out and says
what it is.
"""

from datetime import date, datetime
from typing import Annotated, Self

from ninja import Schema
from pydantic import Field, model_validator

from core.domain import (
    AttachmentKind,
    Channel,
    CheckStatus,
    DecisionLane,
    DecisionOutcome,
    ItemStatus,
    Market,
    Product,
    ReopenReason,
    RiskTier,
    TakedownState,
    TermsField,
    VersionOrigin,
)
from reviews.diff import DiffOp
from reviews.filters import ItemFilter, ItemSort
from reviews.search import SearchMode

# ReviewItem.tags is varchar(50)[]: reject what the column can't hold rather than let Postgres truncate it.
Tag = Annotated[str, Field(min_length=1, max_length=50)]


# --- shared pieces ---------------------------------------------------------------------------------------------


class PartyRefOut(Schema):
    """A person or partner shown in a cell."""

    id: int
    name: str


class SpanOut(Schema):
    start: int
    end: int


# --- queue -----------------------------------------------------------------------------------------------------


class ItemRowOut(Schema):
    id: int
    key: str = Field(examples=["CP-1042"])
    title: str
    product: Product
    channel: Channel
    status: ItemStatus
    round: int
    risk_tier: RiskTier
    reopen_reason: ReopenReason | None
    llm_check_status: CheckStatus
    is_legacy: bool
    markets: list[Market]
    tags: list[str]
    open_findings_count: int
    submitted_at: datetime
    updated_at: datetime
    age_days: int
    planned_first_run: date | None
    planned_last_run: date | None
    current_version_n: int | None
    partner: PartyRefOut | None
    owner: PartyRefOut | None
    assignee: PartyRefOut | None


class ItemPageOut(Schema):
    rows: list[ItemRowOut]
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page; null on the last page.")


class StatusCountOut(Schema):
    status: ItemStatus
    count: int


class QueueStatsOut(Schema):
    open: int
    mine: int
    unassigned: int
    needs_rereview: int
    waiting_over_3_days: int
    by_status: list[StatusCountOut]


# --- intake and item detail ------------------------------------------------------------------------------------


class SubmitItemIn(Schema):
    title: str = Field(min_length=1, max_length=300)
    product: Product
    channel: Channel
    partner_id: int | None = Field(default=None, description="Required for affiliate channels.")
    markets: list[Market] = Field(min_length=1)
    planned_first_run: date
    planned_last_run: date | None = None
    content_text: str = Field(min_length=1, max_length=100_000)
    is_prescreen: bool = Field(default=False, description="A prescreened firm offer (FCRA).")
    source_url: str | None = Field(default=None, max_length=2000, description="Where the copy was fetched from.")
    tags: list[Tag] = Field(default_factory=list, max_length=20)


class FetchCopyIn(Schema):
    url: str = Field(min_length=8, max_length=2000, pattern=r"^https?://")


class FetchedCopyOut(Schema):
    url: str
    title: str | None
    content_text: str


class ItemUpdateIn(Schema):
    """Inline edits. Omitted fields are left as they are."""

    tags: list[Tag] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=10_000)
    risk_tier: RiskTier | None = Field(default=None, description="Reviewers and leads only; recorded as an override.")


class OfferTermsRefOut(Schema):
    id: int
    product: Product
    version: int


class TermsRefOut(Schema):
    field: TermsField
    span: SpanOut
    quote: str
    quoted_value: str = Field(description="Decimal as a string, e.g. '12.99'.")
    offer_terms: OfferTermsRefOut


class VersionSummaryOut(Schema):
    id: int
    n: int
    origin: VersionOrigin
    author: PartyRefOut
    created_at: datetime
    based_on_n: int | None


class VersionOut(VersionSummaryOut):
    content_text: str
    content_sha256: str
    terms_refs: list[TermsRefOut]


class EvidenceOut(Schema):
    attachment_id: int
    sha256: str
    kind: AttachmentKind
    original_name: str


class DecisionOut(Schema):
    id: int
    version_n: int
    outcome: DecisionOutcome
    lane: DecisionLane
    approver: PartyRefOut
    reason: str
    ruleset_date: date
    engine_version: str = Field(description="The code-check engine version the findings came from; '' if unknown.")
    expires_at: datetime | None
    llm_override_reason: str | None
    ai_review_carried_from_n: int | None
    terms_versions: list[OfferTermsRefOut]
    evidence: list[EvidenceOut]
    decided_at: datetime


class ItemDetailOut(ItemRowOut):
    notes: str
    is_prescreen: bool
    risk_tier_overridden: bool
    source_url: str | None
    legacy_ref: str | None
    legacy_submitter: str
    legacy_reviewer: str
    legacy_history: str
    approved_at: datetime | None
    approval_expires_at: datetime | None
    retention_until: date | None
    current_version: VersionOut | None
    versions: list[VersionSummaryOut]
    latest_decision: DecisionOut | None
    live_placements_count: int


class ResubmitIn(Schema):
    """A new version after changes were requested (or a new round from withdrawn)."""

    content_text: str = Field(min_length=1, max_length=100_000)
    note: str = Field(default="", max_length=2000, description="What changed, for the reviewer.")


class NewRoundIn(Schema):
    content_text: str | None = Field(
        default=None, max_length=100_000, description="Omit to start from the latest version (or the generated one)."
    )


class DiffSegmentOut(Schema):
    op: DiffOp
    text: str


class VersionDiffOut(Schema):
    from_n: int
    to_n: int
    segments: list[DiffSegmentOut]


# --- comments and attachments ----------------------------------------------------------------------------------


class CommentIn(Schema):
    body: str = Field(min_length=1, max_length=10_000)
    version_n: int | None = Field(default=None, description="Defaults to the current version.")
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=1)
    mention_user_ids: list[int] = Field(default_factory=list, max_length=20)


class CommentOut(Schema):
    id: int
    version_n: int
    author: PartyRefOut
    body: str
    span: SpanOut | None
    mentions: list[PartyRefOut]
    created_at: datetime


class AttachmentOut(Schema):
    id: int
    kind: AttachmentKind
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: PartyRefOut
    uploaded_at: datetime
    download_url: str


# --- assignment ------------------------------------------------------------------------------------------------


class AssignIn(Schema):
    assignee_id: int | None = Field(description="Null sends the item back to the unassigned pool.")
    reason: str = Field(default="", max_length=500)


class BulkAssignIn(Schema):
    item_ids: list[int] = Field(min_length=1, max_length=500)
    assignee_id: int | None
    reason: str = Field(default="", max_length=500)


class BulkSkippedOut(Schema):
    item_id: int
    code: str = Field(description="Why it was skipped, e.g. 'open_findings_block_decision'.")
    message: str


class BulkResultOut(Schema):
    succeeded: list[int]
    skipped: list[BulkSkippedOut]


# --- placements ------------------------------------------------------------------------------------------------


class PlacementIn(Schema):
    location: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=2000)
    first_run: date
    last_run: date | None = None
    monitored: bool = False


class PlacementUpdateIn(Schema):
    last_run: date | None = None
    monitored: bool | None = None


class PlacementOut(Schema):
    id: int
    approved_version_n: int
    location: str
    url: str | None
    first_run: date
    last_run: date | None
    monitored: bool
    takedown_state: TakedownState | None
    takedown_requested_at: datetime | None
    takedown_confirmed_at: datetime | None
    is_live: bool
    created_by: PartyRefOut
    created_at: datetime


# --- decisions -------------------------------------------------------------------------------------------------


class DecisionIn(Schema):
    outcome: DecisionOutcome
    version_n: int = Field(description="The exact version decided on; stale if a newer version exists.")
    reason: str = Field(min_length=1, max_length=10_000)
    evidence_attachment_ids: list[int] = Field(default_factory=list, max_length=50)
    llm_override_reason: str | None = Field(
        default=None, max_length=2000, description="Required to approve when the AI check failed."
    )
    edited_content_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=100_000,
        description=(
            "Approve with edits: the reviewer's v+1, which is what's approved. If v+1 raises findings, the response "
            "is 409 findings_need_triage and v+1 becomes current; triage, then post approved_with_edits again on "
            "v+1 without this field (and with llm_override_reason again if the AI check failed)."
        ),
    )

    @model_validator(mode="after")
    def _edits_only_with_edits(self) -> Self:
        if self.edited_content_text is not None and self.outcome is not DecisionOutcome.APPROVED_WITH_EDITS:
            raise ValueError("edited_content_text is only allowed with approved_with_edits")
        return self


class ReaffirmIn(Schema):
    reason: str = Field(min_length=1, max_length=10_000)
    llm_override_reason: str | None = Field(
        default=None, max_length=2000, description="Required when the version's AI check failed."
    )


class PullIn(Schema):
    reason: str = Field(min_length=1, max_length=10_000)
    placement_ids: list[int] = Field(default_factory=list, description="Defaults to every live placement.")


# --- saved views -----------------------------------------------------------------------------------------------


class SavedViewIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    filters: ItemFilter
    sort: ItemSort = ItemSort.QUEUE
    columns: list[str] = Field(default_factory=list, max_length=50)


class SavedViewOut(SavedViewIn):
    id: int
    created_at: datetime


# --- library ---------------------------------------------------------------------------------------------------


class SnippetPartOut(Schema):
    text: str
    highlighted: bool


class SearchHitOut(Schema):
    item_id: int
    key: str
    title: str
    status: ItemStatus
    product: Product
    channel: Channel
    partner_name: str | None
    version_id: int
    version_n: int
    snippet: list[SnippetPartOut] = Field(description="Plain-text parts; render highlighted parts with <mark>.")
    score: float
    version_outcome: DecisionOutcome | None = Field(
        description="The latest decision on the matched version (not the item's latest), or null if undecided."
    )
    version_decided_at: datetime | None


class SearchResultsOut(Schema):
    mode: SearchMode
    query: str
    hits: list[SearchHitOut]
