"""`ItemFilter`: the one filter shape shared by the queue API, saved views, export, and the assistant's tools
(decisions.md "Data"). `reviews.selectors.filter_items` is the only place it becomes SQL."""

from datetime import date, datetime
from enum import StrEnum

from ninja import Schema
from pydantic import Field

from core.domain import Channel, ItemStatus, Market, Product, ReopenReason, RiskTier


class ItemSort(StrEnum):
    # Re-reviews of live content first, then risk tier, then age (spec §4.3 Review). With no status filter,
    # limited to the queue statuses (submitted, in_review, needs_rereview).
    QUEUE = "queue"
    OLDEST = "oldest"
    NEWEST = "newest"
    UPDATED = "updated"  # most recently changed first
    TITLE = "title"


class ItemFilter(Schema):
    """Every field narrows the result; list fields match any of their values (tags: all of them).
    Empty means "no constraint". `mine` and `submitted_by_me` are relative to the viewer, so a saved view
    like "My queue" works for whoever opens it."""

    q: str | None = Field(default=None, max_length=200, description="Title contains, or a display key like CP-1042.")
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
    waiting_more_than_days: int | None = Field(default=None, ge=0, description="Submitted more than N days ago.")
    run_from: date | None = Field(default=None, description="Has a placement running on or after this date.")
    run_to: date | None = Field(default=None, description="Has a placement running on or before this date.")
