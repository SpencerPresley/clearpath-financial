from datetime import date, datetime

from ninja import Schema
from pydantic import Field

from accounts.schemas import EMAIL_PATTERN
from core.domain import FindingSource, FindingState, PartnerStatus, PartnerType, Severity
from reviews.schemas import AttachmentOut


class PartnerRowOut(Schema):
    id: int
    name: str
    type: PartnerType
    status: PartnerStatus
    item_count: int
    approved_count: int
    open_findings_count: int
    last_submitted_at: datetime | None


class RepeatIssueOut(Schema):
    rule_id: str
    rule_title: str | None = Field(description="The rule's title; null for a rule the registry doesn't know.")
    citation: str
    count: int
    items: int
    last_seen_at: datetime


class PartnerDetailOut(PartnerRowOut):
    website: str
    contact_email: str
    agreement_signed_on: date | None
    notes: str
    created_at: datetime
    attachments: list[AttachmentOut]
    repeat_issues: list[RepeatIssueOut]


class PartnerIn(Schema):
    name: str = Field(min_length=1, max_length=200)
    type: PartnerType
    website: str = Field(default="", max_length=200)
    contact_email: str = Field(default="", max_length=254, pattern=rf"^$|{EMAIL_PATTERN}")
    agreement_signed_on: date | None = None
    notes: str = Field(default="", max_length=10_000)


class PartnerUpdateIn(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: PartnerType | None = None
    status: PartnerStatus | None = None
    website: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=254, pattern=rf"^$|{EMAIL_PATTERN}")
    agreement_signed_on: date | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class PartnerFindingOut(Schema):
    id: int
    item_id: int
    item_key: str = Field(examples=["CP-1042"])
    item_title: str
    item_is_legacy: bool
    version_n: int
    rule_id: str = Field(examples=["ftc.material_connection"])
    citation: str = Field(examples=["16 CFR 255.5"])
    source: FindingSource = Field(description="code, llm (shown as 'AI suggestion'), or human checklist.")
    severity: Severity
    state: FindingState
    message: str
    created_at: datetime


class PartnerFindingPageOut(Schema):
    rows: list[PartnerFindingOut]
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page; null on the last page.")
