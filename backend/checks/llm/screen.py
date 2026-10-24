"""Turn the model's raw findings into FindingDrafts, or drop them with a reason. Pure; no model involved.

The order of checks is fixed:
1. the rule is a known LLM rule
2. the rule applies to this item
3. the quote is exact at its span, or occurs once and is re-anchored
4. it isn't a repeat of an earlier LLM finding (same rule, same span)
5. it doesn't overlap a code finding that reports the same problem

Copy rules (spec §5.4) are enforced here rather than trusted to the prompt. A message using banned wording is
replaced by the rule's default message, and that is recorded. The citation always comes from the rule.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from checks.engine.types import FindingDraft, RuleContext, Span
from checks.llm.rules import LLM_RULES_BY_ID, LlmRule
from checks.llm.schema import DroppedFinding, DropReason, RawFinding
from checks.llm.spans import Anchor, anchor_quote
from core.domain import FindingSource

BANNED_WORDING = re.compile(r"\b(?:violat\w*|non-?\s?compliant|noncompliant|illegal\w*|unlawful\w*)", re.IGNORECASE)


@dataclass(frozen=True)
class Adjustment:
    """A change made to a kept finding, recorded so the eval and logs can count it."""

    kind: Literal["reanchored", "reworded"]
    rule_id: str
    quote: str
    detail: str


@dataclass(frozen=True)
class Screened:
    findings: tuple[FindingDraft, ...]
    dropped: tuple[DroppedFinding, ...]
    adjustments: tuple[Adjustment, ...]


def _overlaps(a: Span, b: Span) -> bool:
    return a.start < b.end and b.start < a.end


def _code_duplicate(rule: LlmRule, span: Span, code_findings: Sequence[FindingDraft]) -> str | None:
    """The id of a counterpart code finding that already covers this span. A span-less code finding (something
    missing from the whole ad) covers every passage."""
    for code in code_findings:
        if code.rule_id in rule.code_counterparts and (code.span is None or _overlaps(code.span, span)):
            return code.rule_id
    return None


def _message(rule: LlmRule, raw: str) -> tuple[str, bool]:
    message = raw.strip()
    if not message or BANNED_WORDING.search(message):
        return rule.default_message, True
    return message, False


def screen(
    ctx: RuleContext,
    items: Sequence[RawFinding],
    *,
    rules: Sequence[LlmRule],
    code_findings: Sequence[FindingDraft],
) -> Screened:
    applicable = {rule.spec.id for rule in rules}
    kept: list[FindingDraft] = []
    dropped: list[DroppedFinding] = []
    adjustments: list[Adjustment] = []
    seen: set[tuple[str, Span]] = set()

    def drop(reason: DropReason, item: RawFinding, detail: str = "") -> None:
        dropped.append(DroppedFinding(reason, item.rule_id, item.quote, detail))

    for item in items:
        rule = LLM_RULES_BY_ID.get(item.rule_id)
        if rule is None:
            drop(DropReason.UNKNOWN_RULE, item)
            continue
        if item.rule_id not in applicable:
            drop(DropReason.NOT_APPLICABLE, item)
            continue
        anchor = anchor_quote(ctx.text, item.quote, item.start, item.end)
        if not isinstance(anchor, Anchor):
            drop(DropReason(anchor.value), item, f"model said [{item.start}, {item.end})")
            continue
        span = anchor.span
        if (item.rule_id, span) in seen:
            drop(DropReason.DUPLICATE, item)
            continue
        if (code_rule := _code_duplicate(rule, span, code_findings)) is not None:
            drop(DropReason.DUPLICATES_CODE, item, code_rule)
            continue
        seen.add((item.rule_id, span))
        if anchor.reanchored:
            detail = f"model said [{item.start}, {item.end}), found at [{span.start}, {span.end})"
            adjustments.append(Adjustment("reanchored", item.rule_id, item.quote, detail))
        message, reworded = _message(rule, item.message)
        if reworded:
            adjustments.append(Adjustment("reworded", item.rule_id, item.quote, item.message))
        kept.append(
            FindingDraft(
                rule_id=rule.spec.id,
                source=FindingSource.LLM,
                severity=rule.spec.severity,
                message=message,
                citation=rule.spec.citation,
                suggested_fix=item.suggested_fix.strip() or None,
                span=span,
                quote=ctx.text[span.start : span.end],
            )
        )
    kept.sort(key=lambda f: (f.span.start if f.span is not None else 0, f.rule_id))
    return Screened(tuple(kept), tuple(dropped), tuple(adjustments))
