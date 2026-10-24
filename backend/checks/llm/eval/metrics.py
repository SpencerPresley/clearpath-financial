"""Scoring and cost for the eval. Pure, so the arithmetic is unit-tested without a model."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from checks.llm.review import TokenUsage

# Claude Haiku 5.5, USD per million tokens, prompts up to 100k tokens
# (platform.claude.com/docs/en/about-claude/pricing, fetched 2026-10-24). Cache writes use the default 5m TTL.
HAIKU_5_5_PER_MTOK = {
    "input": Decimal("0.10"),
    "cache_write_5m": Decimal("0.125"),
    "cache_read": Decimal("0.01"),
    "output": Decimal("0.50"),
}
_MTOK = Decimal(1_000_000)


@dataclass(frozen=True)
class RuleScore:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None


MICRO = "(all rules)"


def score(runs: Iterable[tuple[frozenset[str], frozenset[str]]], rule_ids: Iterable[str]) -> Mapping[str, RuleScore]:
    """Per-rule presence scoring over (expected, predicted) rule-id sets, one pair per case run.

    A rule counts once per run: reported at least once when expected is a true positive, whatever the span.
    The MICRO row sums every rule.
    """
    counts = {rule_id: [0, 0, 0] for rule_id in rule_ids}
    for expected, predicted in runs:
        for rule_id, c in counts.items():
            if rule_id in expected and rule_id in predicted:
                c[0] += 1
            elif rule_id in predicted:
                c[1] += 1
            elif rule_id in expected:
                c[2] += 1
    scores = {rule_id: RuleScore(*c) for rule_id, c in counts.items()}
    scores[MICRO] = RuleScore(
        sum(s.tp for s in scores.values()), sum(s.fp for s in scores.values()), sum(s.fn for s in scores.values())
    )
    return scores


def cost_usd(usage: TokenUsage, rates: Mapping[str, Decimal] = HAIKU_5_5_PER_MTOK) -> Decimal:
    """`usage.input_tokens` includes cached tokens (LangChain's convention), so they're priced separately."""
    uncached = max(usage.input_tokens - usage.cache_read_tokens - usage.cache_creation_tokens, 0)
    total = (
        uncached * rates["input"]
        + usage.cache_creation_tokens * rates["cache_write_5m"]
        + usage.cache_read_tokens * rates["cache_read"]
        + usage.output_tokens * rates["output"]
    )
    return total / _MTOK
