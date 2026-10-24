"""The corpus is well-formed and the runner works end to end with a scripted model (no network)."""

from decimal import Decimal

import anthropic
import httpx2

from checks.engine import run_code_checks
from checks.llm.eval.__main__ import demo_terms, main
from checks.llm.eval.corpus import CASES
from checks.llm.eval.metrics import MICRO, RuleScore, cost_usd, score
from checks.llm.eval.runner import INJECTION_CASES, context_for, render, run_eval
from checks.llm.review import TokenUsage
from checks.llm.rules import LLM_RULES_BY_ID, applicable_rules
from checks.llm.tests.fakes import RaisingModel, fake, finding, report
from core.domain import Channel, Product


def test_corpus_size_and_unique_names():
    names = [c.name for c in CASES]
    assert 12 <= len(names) <= 20
    assert len(names) == len(set(names))


def test_cases_build_valid_contexts():
    for case in CASES:
        ctx = context_for(case, demo_terms)
        assert ctx.text == case.text


def test_expected_ids_are_applicable_llm_rules():
    for case in CASES:
        applicable = {r.spec.id for r in applicable_rules(context_for(case, demo_terms))}
        assert case.expected <= applicable, case.name


def test_expected_findings_are_not_code_duplicates():
    # An expected LLM rule must not have a counterpart code finding in the same case; the screen would drop it.
    for case in CASES:
        code_ids = {f.rule_id for f in run_code_checks(context_for(case, demo_terms)).findings}
        for rule_id in case.expected:
            assert not (LLM_RULES_BY_ID[rule_id].code_counterparts & code_ids), (case.name, rule_id)


def test_corpus_covers_products_channels_partners_and_injection():
    assert {c.product for c in CASES} == set(Product)
    channels = {c.channel for c in CASES}
    assert {Channel.AFFILIATE_PAGE, Channel.EMAIL, Channel.SMS, Channel.PAID_SOCIAL, Channel.DIRECT_MAIL} <= channels
    assert sum(1 for c in CASES if c.partner_type is not None) >= 3
    assert {c.name for c in CASES} >= INJECTION_CASES
    assert any("automated reviewers" in c.text for c in CASES if c.name in INJECTION_CASES)
    assert sum(1 for c in CASES if not c.expected) >= 3  # clean cases measure false positives
    expected_rules = set().union(*(c.expected for c in CASES))
    assert expected_rules == set(LLM_RULES_BY_ID)  # every rule has at least one positive case


def test_score_counts():
    runs = [
        (frozenset({"a"}), frozenset({"a", "b"})),
        (frozenset({"a"}), frozenset()),
        (frozenset(), frozenset({"b"})),
    ]
    scores = score(runs, ["a", "b"])
    assert scores["a"] == RuleScore(tp=1, fp=0, fn=1)
    assert scores["b"] == RuleScore(tp=0, fp=2, fn=0)
    assert scores[MICRO] == RuleScore(tp=1, fp=2, fn=1)
    assert scores["a"].precision == 1.0
    assert scores["a"].recall == 0.5
    assert scores["b"].recall is None


def test_cost_uses_cache_rates():
    usage = TokenUsage(input_tokens=3000, output_tokens=200, cache_read_tokens=2000, cache_creation_tokens=500)
    # 500 uncached x 0.10 + 500 write x 0.125 + 2000 read x 0.01 + 200 out x 0.50, per million
    assert cost_usd(usage) == Decimal("0.0002325")


def test_runner_with_scripted_model_renders_report():
    case = next(c for c in CASES if c.name == "pl_paid_social_free_money")
    clean = next(c for c in CASES if c.name == "pl_display_clean")
    model = fake(
        report(finding(case.text, "llm.net_impression", "Get free money in minutes with ClearPath!")),
        report(finding(clean.text, "llm.pressure_tactics", "Check your rate at clearpath.example/loans")),
    )
    runs = run_eval([case, clean], model=model, terms=demo_terms)
    assert [r.predicted for r in runs] == [frozenset({"llm.net_impression"}), frozenset({"llm.pressure_tactics"})]
    text = render(runs)
    assert "llm.net_impression" in text
    assert "clean cases with any LLM finding: 1/1" in text
    assert "cost: $" in text
    assert "overall: precision   50%, recall  100%" in text


def test_runner_records_provider_errors_and_continues():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    model = RaisingModel(messages=iter(()), error=anthropic.APIConnectionError(request=request))
    runs = run_eval(CASES[:2], model=model, terms=demo_terms)
    assert all(r.result is None and r.error for r in runs)
    assert "provider errors: 2" in render(runs)


def test_main_without_api_key_exits_cleanly(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main([]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
