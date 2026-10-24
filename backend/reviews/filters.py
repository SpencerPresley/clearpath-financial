"""`ItemFilter`: the one filter shape shared by the queue API, saved views, export, and the assistant's tools
(decisions.md "Data"). `reviews.selectors.filter_items` is the only place it becomes SQL."""

from datetime import date, datetime
from enum import StrEnum

from ninja import Schema
from pydantic import Field

from core.domain import Channel, ItemStatus, Market, Product, ReopenReason, RiskTier


class ItemSort(StrEnum):
    """One member per order: each runs one direction so a keyset page boundary is a single row comparison.
    Column sorts come in pairs, `x` ascending and `x_desc` the exact reverse."""

    # Re-reviews of live content first, then risk tier, then age: time since the item last entered the queue
    # (spec §4.3 Review). With no status filter, limited to the queue statuses (submitted, in_review, needs_rereview).
    QUEUE = "queue"
    OLDEST = "oldest"  # longest in the queue first: by when the item last entered it (Age)
    NEWEST = "newest"
    UPDATED = "updated"  # most recently changed first
    TITLE = "title"
    TITLE_DESC = "title_desc"
    STATUS = (
        "status"  # draft, then board order: submitted, in review, changes requested, needs re-review, approved, ...
    )
    STATUS_DESC = "status_desc"
    RISK_TIER = "risk_tier"  # low, medium, high
    RISK_TIER_DESC = "risk_tier_desc"
    ASSIGNEE = "assignee"  # by name, case-insensitive; unassigned last
    ASSIGNEE_DESC = "assignee_desc"
    PARTNER = "partner"  # by name, case-insensitive; no partner last
    PARTNER_DESC = "partner_desc"
    OPEN_FINDINGS = "open_findings"  # fewest first
    OPEN_FINDINGS_DESC = "open_findings_desc"
    ROUND = "round"
    ROUND_DESC = "round_desc"


class ItemFilter(Schema):
    """Every field narrows the result; list fields match any of their values (tags: all of them).
    Empty means "no constraint". `mine` and `submitted_by_me` are relative to the viewer, so a saved view
    like "My queue" works for whoever opens it."""

    q: str | None = Field(
        default=None,
        max_length=200,
        description="Title or legacy tracker ID (MCR-26-045) contains, or a display key like CP-1042.",
    )
    status: list[ItemStatus] = Field(default_factory=list)
    product: list[Product] = Field(default_factory=list)
    channel: list[Channel] = Field(default_factory=list)
    partner_id: list[int] = Field(default_factory=list)
    assignee_id: list[int] = Field(default_factory=list)
    owner_id: list[int] = Field(default_factory=list)
    mine: bool = Field(default=False, description="Assigned to the viewer.")
    submitted_by_me: bool = Field(default=False, description="Submitted by the viewer.")
    unassigned: bool = False
    risk_tier: list[RiskTier] = Field(default_factory=list)
    market: list[Market] = Field(default_factory=list)
    tag: list[str] = Field(default_factory=list, description="Items carrying all of these tags.")
    is_legacy: bool | None = None
    has_open_findings: bool | None = None
    reopen_reason: list[ReopenReason] = Field(default_factory=list)
    submitted_after: datetime | None = None
    submitted_before: datetime | None = None
    waiting_more_than_days: int | None = Field(
        default=None,
        ge=0,
        description="Entered the queue more than N days ago (last submission, resubmission, new round or reopen).",
    )
    approved_after: datetime | None = None
    approved_before: datetime | None = None
    approved_within_days: int | None = Field(default=None, ge=0, description="Approved in the last N days.")
    run_from: date | None = Field(default=None, description="Has a placement running on or after this date.")
    run_to: date | None = Field(default=None, description="Has a placement running on or before this date.")
