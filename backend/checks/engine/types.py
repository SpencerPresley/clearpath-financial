"""Value types crossing the engine boundary. Frozen, Django-free, safe to share between workstreams."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from core.domain import (
    AttachmentKind,
    Channel,
    CreditCardTerms,
    FindingSource,
    FixKind,
    Market,
    PartnerType,
    PersonalLoanTerms,
    Product,
    Severity,
)


@dataclass(frozen=True)
class Span:
    """Half-open `[start, end)` offsets into the exact text the check ran on."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if not 0 <= self.start <= self.end:
            raise ValueError(f"span must satisfy 0 <= start <= end, got [{self.start}, {self.end})")


@dataclass(frozen=True)
class RuleSpec:
    id: str
    title: str
    citation: str
    url: str
    severity: Severity
    kind: Literal["code", "human", "llm"]  # "llm": judged by the LLM pre-review (checks.llm), never by the engine
    products: frozenset[Product]
    channels: frozenset[Channel] | None  # None = all channels
    markets: frozenset[Market]
    effective_from: date


@dataclass(frozen=True)
class RuleContext:
    text: str
    product: Product
    channel: Channel
    markets: frozenset[Market]
    partner_type: PartnerType | None
    attachment_kinds: frozenset[AttachmentKind]
    terms: PersonalLoanTerms | CreditCardTerms | None
    today: date

    def __post_init__(self) -> None:
        if self.terms is not None and self.terms.product != self.product:
            raise ValueError(f"terms are for {self.terms.product}, but the item is {self.product}")


@dataclass(frozen=True)
class FindingDraft:
    rule_id: str
    source: FindingSource
    severity: Severity
    message: str
    citation: str
    suggested_fix: str | None
    span: Span | None
    quote: str | None  # == text[span.start:span.end] when span is set
    # What Apply does with the fix (see `FixKind`); None with no fix. `replacement_text` only for replace/insert.
    fix_kind: FixKind | None = None
    replacement_text: str | None = None


@dataclass(frozen=True)
class TermsRefDraft:
    """An offer-terms claim found in the copy. `field` is an attribute of the product's terms model, or
    "example_payment" for the payment in a representative example."""

    field: str
    span: Span
    quoted_value: Decimal


@dataclass(frozen=True)
class CheckResult:
    findings: tuple[FindingDraft, ...]
    terms_refs: tuple[TermsRefDraft, ...]
