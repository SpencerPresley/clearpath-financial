"""Run the corpus through code checks + review_copy and render the report. Model-agnostic, so it's testable."""

import statistics
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from langchain_core.language_models import BaseChatModel

from checks.engine import RuleContext, run_code_checks
from checks.llm.eval.corpus import EvalCase
from checks.llm.eval.metrics import MICRO, cost_usd, score
from checks.llm.review import LlmReviewResult, LlmUnavailable, TokenUsage, review_copy
from checks.llm.rules import LLM_RULES
from core.domain import CreditCardTerms, PersonalLoanTerms, Product

INJECTION_CASES = frozenset({"affiliate_injection"})
EVAL_DATE = date(2026, 10, 24)  # the corpus is written against the offer terms and rules in effect on this date


@dataclass(frozen=True)
class CaseRun:
    case: EvalCase
    result: LlmReviewResult | None
    error: str | None  # set when the provider failed (LlmUnavailable)

    @property
    def predicted(self) -> frozenset[str]:
        return frozenset(f.rule_id for f in self.result.findings) if self.result else frozenset()


def context_for(case: EvalCase, terms: Callable[[Product], PersonalLoanTerms | CreditCardTerms | None]) -> RuleContext:
    return RuleContext(
        text=case.text,
        product=case.product,
        channel=case.channel,
        markets=frozenset(case.markets),
        partner_type=case.partner_type,
        attachment_kinds=frozenset(case.attachments),
        terms=terms(case.product),
        today=EVAL_DATE,
    )


def run_eval(
    cases: Sequence[EvalCase],
    *,
    model: BaseChatModel,
    terms: Callable[[Product], PersonalLoanTerms | CreditCardTerms | None],
    repeat: int = 1,
) -> list[CaseRun]:
    runs: list[CaseRun] = []
    for _ in range(repeat):
        for case in cases:
            ctx = context_for(case, terms)
            code = run_code_checks(ctx).findings
            try:
                result = review_copy(ctx, code_findings=code, model=model)
            except LlmUnavailable as error:
                runs.append(CaseRun(case, None, f"{error} (retryable={error.retryable})"))
                continue
            runs.append(CaseRun(case, result, None))
    return runs


def _ids(ids: frozenset[str]) -> str:
    return ", ".join(sorted(i.removeprefix("llm.") for i in ids)) or "-"


def _pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.0%}"


def render(runs: Sequence[CaseRun]) -> str:
    lines = [f"{'case':34} {'expected':34} {'predicted':34} drop  ms   valid"]
    for run in runs:
        if run.result is None:
            lines.append(f"{run.case.name:34} provider error: {run.error}")
            continue
        r = run.result
        lines.append(
            f"{run.case.name:34} {_ids(run.case.expected):34} {_ids(run.predicted):34} "
            f"{len(r.dropped):4} {r.latency_ms:5} {'yes' if r.output_valid else 'NO'}"
        )

    results = [run.result for run in runs if run.result is not None]
    # Only valid outputs are scored. An invalid one (prose, truncated) has no findings, and counting it would book a
    # clean case as a true negative and a positive case as a miss; it's reported on its own line instead.
    completed = [run for run in runs if run.result is not None and run.result.output_valid]
    invalid = [run.case.name for run in runs if run.result is not None and not run.result.output_valid]
    scores = score(((run.case.expected, run.predicted) for run in completed), (r.spec.id for r in LLM_RULES))
    lines += ["", f"{'rule':34} {'tp':>3} {'fp':>3} {'fn':>3} precision recall"]
    for rule_id, s in scores.items():
        lines.append(f"{rule_id:34} {s.tp:3} {s.fp:3} {s.fn:3} {_pct(s.precision):>9} {_pct(s.recall):>6}")

    clean = [run for run in completed if not run.case.expected]
    clean_with_findings = [run.case.name for run in clean if run.predicted]
    usage = sum((r.usage for r in results), TokenUsage())
    cost = cost_usd(usage)
    drops = Counter(d.reason.value for r in results for d in r.dropped)
    adjustments = Counter(a.kind for r in results for a in r.adjustments)
    latencies = [r.latency_ms for r in results]
    lines += [
        "",
        (
            f"runs: {len(runs)}  scored: {len(completed)}  provider errors: {len(runs) - len(results)}  "
            f"invalid outputs (not scored): {len(invalid)} {invalid or ''}"
        ),
        f"clean cases with any LLM finding: {len(clean_with_findings)}/{len(clean)} {clean_with_findings or ''}",
        f"dropped: {dict(sorted(drops.items())) or 'none'}",
        f"adjustments: {dict(sorted(adjustments.items())) or 'none'}",
        (
            f"tokens: input {usage.input_tokens} (cache read {usage.cache_read_tokens}, cache write "
            f"{usage.cache_creation_tokens}), output {usage.output_tokens}"
        ),
        f"cost: ${cost:.4f} total, ${cost / max(len(results), 1):.5f} per review (Haiku 5.5 rates for any model)",
    ]
    if latencies:
        lines.append(f"latency: median {statistics.median(latencies):.0f} ms, max {max(latencies)} ms")
    for run in completed:
        if run.case.name in INJECTION_CASES:
            lines.append(
                f"injection {run.case.name}: predicted [{_ids(run.predicted)}], expected [{_ids(run.case.expected)}]"
            )
    micro = scores[MICRO]
    lines.append(f"overall: precision {_pct(micro.precision)}, recall {_pct(micro.recall)}")
    return "\n".join(lines)
