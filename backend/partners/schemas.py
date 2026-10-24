from datetime import date, datetime

from ninja import Schema
from pydantic import Field

from accounts.schemas import EMAIL_PATTERN
from core.domain import PartnerStatus, PartnerType
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
    contact_email: str | None = Field(default=None, max_length=254)
    agreement_signed_on: date | None = None
    notes: str | None = Field(default=None, max_length=10_000)
