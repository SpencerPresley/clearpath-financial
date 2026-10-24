from datetime import datetime

from ninja import Schema
from pydantic import Field

from core.domain import CheckStatus, DriftResult, DriftTrigger, Severity
from reviews.schemas import DiffSegmentOut, PartyRefOut


class PageFindingOut(Schema):
    """A code finding on the fetched page's text (not stored as a Finding: it belongs to no version)."""

    rule_id: str
    citation: str
    severity: Severity
    message: str
    suggested_fix: str | None
    quote: str | None
    new: bool = Field(description="The rule doesn't fire on the approved copy itself.")


class SnapshotOut(Schema):
    """One drift check of a placement's page."""

    id: int
    placement_id: int
    status: CheckStatus
    trigger: DriftTrigger
    requested_by: PartyRefOut | None = Field(description="Null for the daily sweep.")
    requested_at: datetime
    finished_at: datetime | None
    url: str
    final_url: str | None
    http_status: int | None
    title: str | None
    compared_version_n: int | None = Field(description="The latest approved version the page was compared with.")
    result: DriftResult | None = Field(description="Set when status is succeeded.")
    score: float | None = Field(description="0-100: how much of the approved copy the page keeps.")
    diff: list[DiffSegmentOut] = Field(description="Approved copy -> page, for a modified result.")
    findings: list[PageFindingOut]
    new_blocking_count: int = Field(
        description="Blocking findings on the page whose rule doesn't fire on the approved copy. On an unchanged "
        "result this is the attention state: partner text beside intact approved copy."
    )
    error_code: str | None = Field(description="Why a failed check failed (e.g. timeout, address_not_allowed).")
    error_message: str | None
    reopened_item: bool = Field(description="This check sent the item to re-review.")


class DemoPageRefOut(Schema):
    slug: str
    partner: str
    edited: bool
    edit_summary: str
    expected: str


class PlacementDriftOut(Schema):
    placement_id: int
    location: str
    url: str
    monitored: bool
    is_live: bool
    latest: SnapshotOut | None
    failure_streak: int = Field(
        description="How many of the latest checks in a row couldn't fetch the page (404, outage, ...), up to 3; "
        "at 3 on a live placement the approved copy counts as missing and the item is reopened."
    )
    demo_page: DemoPageRefOut | None = Field(description="Set when the URL is one of this site's demo pages.")


class ItemDriftOut(Schema):
    item_id: int
    placements: list[PlacementDriftOut]


class DemoPageOut(Schema):
    slug: str
    partner: str
    url: str
    edited: bool
    edit_summary: str
    expected: str


class DemoPageUpdateIn(Schema):
    edited: bool
