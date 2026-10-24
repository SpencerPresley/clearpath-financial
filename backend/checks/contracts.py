"""Engine-facing types. The code rules engine (workstream C, `checks/engine/`) and the LLM pre-review
(workstream D) take a `CheckInput` and produce drafts; `checks.services` persists them.

Plain frozen dataclasses: rules are pure functions over these, with no Django imports.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Self

from core.domain import (
    AttachmentKind,
    Channel,
    CreditCardTerms,
    FindingSource,
    Market,
    PersonalLoanTerms,
    Product,
    Severity,
    TermsField,
)


@dataclass(frozen=True)
class Span:
    """Half-open `[start, end)` character offsets into a version's `content_text`."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if not 0 <= self.start < self.end:
            raise ValueError(f"span must satisfy 0 <= start < end, got [{self.start}, {self.end})")

    def of(self, text: str) -> str:
        return text[self.start : self.end]


@dataclass(frozen=True)
class CheckInput:
    """Everything a rule may look at (spec §4.2 ruling 7: attachment kinds count, not just the text)."""

    text: str
    product: Product
    channel: Channel
    markets: frozenset[Market]
    attachment_kinds: frozenset[AttachmentKind]
    is_prescreen: bool
    has_partner: bool
    offer_terms: PersonalLoanTerms | CreditCardTerms | None
    offer_terms_id: int | None = None


@dataclass(frozen=True)
class FindingDraft:
    rule_id: str
    citation: str
    source: FindingSource
    severity: Severity
    message: str
    suggested_fix: str = ""
    span: Span | None = None
    quote: str | None = None

    def __post_init__(self) -> None:
        if (self.span is None) != (self.quote is None):
            raise ValueError("quote is set exactly when span is set")


@dataclass(frozen=True)
class TermsRefDraft:
    field: TermsField
    span: Span
    quote: str
    value: Decimal


@dataclass(frozen=True)
class CodeCheckResult:
    findings: tuple[FindingDraft, ...]
    terms_refs: tuple[TermsRefDraft, ...]
    # Identifies the rule set that produced this result; part of the check cache key.
    ruleset_key: str
    ruleset_date: date | None = None

    @classmethod
    def empty(cls) -> Self:
        return cls(findings=(), terms_refs=(), ruleset_key="none")
