from datetime import datetime

from ninja import Schema
from pydantic import Field

from core.domain import AttachmentKind, Channel, FindingSource, FindingState, Market, Product, Severity, TermsField
from reviews.schemas import PartyRefOut, SpanOut


class FindingOut(Schema):
    id: int
    version_n: int
    rule_id: str = Field(examples=["reg_z.trigger_terms"])
    citation: str = Field(examples=["Reg Z 1026.24(a)"])
    source: FindingSource = Field(description="code, llm (shown as 'AI suggestion'), or human checklist.")
    severity: Severity
    state: FindingState
    span: SpanOut | None
    quote: str | None
    message: str
    suggested_fix: str
    reason: str
    resolved_by: PartyRefOut | None
    resolved_at: datetime | None
    carried_from_id: int | None = Field(description="Set when a dismissal was carried forward from an earlier version.")
    created_at: datetime


class FindingAcceptIn(Schema):
    note: str = Field(default="", max_length=2000)


class FindingDismissIn(Schema):
    reason: str = Field(min_length=1, max_length=2000)


class CheckPreviewIn(Schema):
    """Live code checks while the marketer types (spec §4.3 Intake: under 300 ms)."""

    content_text: str = Field(max_length=100_000)
    product: Product
    channel: Channel
    markets: list[Market] = Field(min_length=1)
    partner_id: int | None = None
    is_prescreen: bool = False
    attachment_kinds: list[AttachmentKind] = Field(default_factory=list)


class FindingDraftOut(Schema):
    rule_id: str
    citation: str
    source: FindingSource
    severity: Severity
    message: str
    suggested_fix: str
    span: SpanOut | None
    quote: str | None


class TermsRefDraftOut(Schema):
    field: TermsField
    span: SpanOut
    quote: str
    value: str


class CheckPreviewOut(Schema):
    findings: list[FindingDraftOut]
    terms_refs: list[TermsRefDraftOut]
    ruleset_key: str
