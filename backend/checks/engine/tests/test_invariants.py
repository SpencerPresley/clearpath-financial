"""Properties every result must have, whatever the copy: exact spans, deterministic order, no suppression by
injected instructions, and keystroke-speed performance."""

import random
import re
import statistics
import time
from decimal import Decimal
from pathlib import Path

import pytest

from checks.engine import RULES, CheckResult, FindingDraft, human_checklist, run_code_checks
from core.domain import Channel, Market, PartnerType, Product

from .samples import INJECTION, SAMPLES, Sample
from .test_samples import check, context

# Neutral filler, plus the characters real pasted copy carries: en/em dashes, curly quotes, NBSP, emoji.
_FILLER = ["Hello", "there", "\u2013", "\u2014", "\u2019s", "\u201cquoted\u201d", "\u00a0", "\U0001f3e0", "\t", "ok"]
_PERCENT_OR_MONEY = re.compile(r"^\d+(?:\.\d+)?\s?(?:%|percent)$|^\$")
_BANNED = re.compile(r"\b(?:violations?|non-?compliant|illegal|unlawful)\b", re.IGNORECASE)
_PERF_BUDGET_S = 0.100
_PERF_TEXT_CHARS = 5000


def _prefix(rng: random.Random) -> str:
    return " ".join(rng.choice(_FILLER) for _ in range(rng.randint(1, 12))) + "\n\n"


def _assert_spans_exact(text: str, result: CheckResult) -> None:
    for f in result.findings:
        if f.span is None:
            assert f.quote is None
        else:
            assert 0 <= f.span.start <= f.span.end <= len(text)
            assert f.quote == text[f.span.start : f.span.end]
    for ref in result.terms_refs:
        quote = text[ref.span.start : ref.span.end]
        assert quote
        if _PERCENT_OR_MONEY.match(quote) or quote.isdigit():
            number = re.sub(r"[^\d.]", "", quote)
            assert Decimal(number) * (1000 if quote.lower().endswith("k") else 1) == ref.quoted_value


def _key(f: FindingDraft, shift: int = 0) -> tuple[object, ...]:
    span = None if f.span is None else (f.span.start - shift, f.span.end - shift)
    return (f.rule_id, f.severity, f.message, span, f.quote)


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_quotes_equal_text_at_span(sample: Sample) -> None:
    _assert_spans_exact(sample.text, check(sample))


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_spans_shift_exactly_with_unicode_prefixes(sample: Sample) -> None:
    rng = random.Random(sample.name)  # noqa: S311 - seeded fuzzing, not cryptography
    base = {_key(f) for f in check(sample).findings}
    for _ in range(25):
        prefix = _prefix(rng)
        text = prefix + sample.text
        result = check(sample, text)
        _assert_spans_exact(text, result)
        assert {_key(f, len(prefix)) for f in result.findings} == base


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_findings_are_sorted_and_deterministic(sample: Sample) -> None:
    first, second = check(sample), check(sample)
    assert first == second
    anchored = [f.span.start for f in first.findings if f.span is not None]
    assert anchored == sorted(anchored)
    seen_unanchored = False
    for f in first.findings:
        seen_unanchored = seen_unanchored or f.span is None
        assert f.span is None or not seen_unanchored, "span-less findings come last"


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
@pytest.mark.parametrize("position", ["start", "end"])
def test_injected_instructions_do_not_suppress_findings(sample: Sample, position: str) -> None:
    """Spec §7: copy telling reviewers it was pre-approved changes nothing that was already found. The injected
    sentence is itself copy, so a finding *inside* it (it says "pre-approved") is correct and expected."""
    block = INJECTION + "\n\n" if position == "start" else "\n\n" + INJECTION
    text = block + sample.text if position == "start" else sample.text + block
    shift = len(block) if position == "start" else 0
    region = (0, len(block)) if position == "start" else (len(sample.text), len(text))

    base = {_key(f) for f in check(sample).findings}
    injected = check(sample, text).findings
    assert base <= {_key(f, shift) for f in injected}
    for f in injected:
        if _key(f, shift) in base:
            continue
        assert f.span is not None, f"new span-less finding {f.rule_id} after injection"
        assert region[0] <= f.span.start
        assert f.span.end <= region[1]


def test_injection_is_itself_flagged_as_a_preapproval_claim() -> None:
    sample = SAMPLES[0]
    result = check(sample, sample.text + "\n\n" + INJECTION)
    assert "pre-approved" in [f.quote for f in result.findings if f.rule_id == "claims.preapproved"]


def _all_findings() -> list[FindingDraft]:
    out: list[FindingDraft] = []
    for sample in SAMPLES:
        out += check(sample).findings
        out += human_checklist(context(sample))
    return out


def test_messages_are_suggestions_never_verdicts() -> None:
    for f in _all_findings():
        assert not _BANNED.search(f.message), f.message
        assert not _BANNED.search(f.suggested_fix or ""), f.suggested_fix
    for spec in RULES.values():
        assert not _BANNED.search(spec.title), spec.title


def test_samples_exercise_every_rule_family() -> None:
    fired = {f.rule_id for f in _all_findings()}
    families = {rule_id.split(".")[0] for rule_id in fired}
    assert {"pricing", "closed_end", "card", "mortgage", "claims", "email", "sms", "endorsement", "ca", "human"} <= (
        families
    )


def test_every_rule_is_named_in_some_test_module() -> None:
    """Each rule needs its own should-flag and shouldn't-flag fixtures; a rule nobody names has neither."""
    sources = "".join(p.read_text(encoding="utf-8") for p in Path(__file__).parent.glob("test_*.py"))
    sources += Path(__file__).with_name("samples.py").read_text(encoding="utf-8")
    missing = [rule_id for rule_id in RULES if f'"{rule_id}"' not in sources]
    assert not missing


def _perf_text() -> str:
    text = ""
    while len(text) < _PERF_TEXT_CHARS:
        text += "\n\n".join(s.text for s in SAMPLES) + "\n\n"
    return text[:_PERF_TEXT_CHARS]


@pytest.mark.parametrize("product", list(Product))
def test_checks_run_in_under_100ms_on_a_5kb_ad(product: Product) -> None:
    text = _perf_text()
    sample = Sample(
        name="perf",
        text=text,
        product=product,
        channel=Channel.EMAIL,
        expected=frozenset(),
        markets=(Market.NATIONAL, Market.CA),
        partner_type=PartnerType.AFFILIATE,
    )
    ctx = context(sample)
    run_code_checks(ctx)  # warm caches (compiled config phrases)
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        result = run_code_checks(ctx)
        timings.append(time.perf_counter() - start)
    assert result.findings
    assert statistics.median(timings) < _PERF_BUDGET_S, timings
