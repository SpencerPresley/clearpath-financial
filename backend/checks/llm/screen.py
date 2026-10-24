"""Turn the model's raw findings into FindingDrafts, or drop them with a reason. Pure; no model involved.

The order of checks is fixed:
1. the rule is a known LLM rule
2. the rule applies to this item
3. the quote is exact at its span, or occurs once and is re-anchored
4. it doesn't overlap an earlier LLM finding of the same rule
5. it doesn't overlap a code finding that reports the same problem

Copy rules (spec §5.4) are enforced here rather than trusted to the prompt. A message using banned wording is
replaced by the rule's default message; a suggested fix using it is removed. Both are recorded. The citation
always comes from the rule.
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

_DASHES = "".join(chr(c) for c in range(0x2010, 0x2015))  # hyphen, non-breaking hyphen, figure/en/em dash
BANNED_WORDING = re.compile(
    rf"\b(?:violat\w*|non[-{_DASHES}\s]?complian(?:t|ce)\w*|not\s+compliant|illegal\w*|unlawful\w*)", re.IGNORECASE
)


@dataclass(frozen=True)
class Adjustment:
    """A change made to a kept finding, recorded so the eval and logs can count it."""

    kind: Literal["reanchored", "reworded", "fix_removed"]
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


def _fix(raw: str) -> tuple[str | None, bool]:
    fix = raw.strip()
    if fix and BANNED_WORDING.search(fix):
        return None, True
    return fix or None, False


def _locate(
    item: RawFinding,
    text: str,
    applicable: set[str],
    seen: dict[str, list[Span]],
    code_findings: Sequence[FindingDraft],
) -> tuple[LlmRule, Anchor] | DroppedFinding:
    """Checks 1-5: where the finding sits, or why it's dropped."""

    def drop(reason: DropReason, detail: str = "") -> DroppedFinding:
        return DroppedFinding(reason, item.rule_id, item.quote, detail)

    rule = LLM_RULES_BY_ID.get(item.rule_id)
    if rule is None:
        return drop(DropReason.UNKNOWN_RULE)
    if item.rule_id not in applicable:
        return drop(DropReason.NOT_APPLICABLE)
    anchor = anchor_quote(text, item.quote, item.start, item.end)
    if not isinstance(anchor, Anchor):
        return drop(DropReason(anchor.value), f"model said [{item.start}, {item.end})")
    # Same rule on an overlapping passage ("free money" inside "free money in minutes!") is one problem.
    if any(_overlaps(anchor.span, earlier) for earlier in seen.get(item.rule_id, ())):
        return drop(DropReason.DUPLICATE)
    if (code_rule := _code_duplicate(rule, anchor.span, code_findings)) is not None:
        return drop(DropReason.DUPLICATES_CODE, code_rule)
    return rule, anchor


def _finding(item: RawFinding, rule: LlmRule, anchor: Anchor, text: str) -> tuple[FindingDraft, list[Adjustment]]:
    span = anchor.span
    adjustments: list[Adjustment] = []
    if anchor.reanchored:
        detail = f"model said [{item.start}, {item.end}), found at [{span.start}, {span.end})"
        adjustments.append(Adjustment("reanchored", item.rule_id, item.quote, detail))
    message, reworded = _message(rule, item.message)
    if reworded:
        adjustments.append(Adjustment("reworded", item.rule_id, item.quote, item.message))
    fix, fix_removed = _fix(item.suggested_fix)
    if fix_removed:
        adjustments.append(Adjustment("fix_removed", item.rule_id, item.quote, item.suggested_fix))
    finding = FindingDraft(
        rule_id=rule.spec.id,
        source=FindingSource.LLM,
        severity=rule.spec.severity,
        message=message,
        citation=rule.spec.citation,
        suggested_fix=fix,
        span=span,
        quote=text[span.start : span.end],
    )
    return finding, adjustments


def screen(
    ctx: RuleContext,
    items: Sequence[RawFinding],
    *,
    rules: Sequence[LlmRule],
    code_findings: Sequence[FindingDraft],
) -> Screened:
    applicable = {rule.spec.id for rule in rules}
    kept: list[tuple[Span, FindingDraft]] = []
    dropped: list[DroppedFinding] = []
    adjustments: list[Adjustment] = []
    seen: dict[str, list[Span]] = {}
    for item in items:
        located = _locate(item, ctx.text, applicable, seen, code_findings)
        if isinstance(located, DroppedFinding):
            dropped.append(located)
            continue
        rule, anchor = located
        seen.setdefault(item.rule_id, []).append(anchor.span)
        finding, changes = _finding(item, rule, anchor, ctx.text)
        kept.append((anchor.span, finding))
        adjustments.extend(changes)
    kept.sort(key=lambda pair: (pair[0].start, pair[1].rule_id))
    return Screened(tuple(f for _, f in kept), tuple(dropped), tuple(adjustments))
