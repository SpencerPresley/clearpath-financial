from dataclasses import FrozenInstanceError, replace
from datetime import date

import pytest

from checks.engine import RULES, RULESET_VERSION, RuleContext, Span, human_checklist, run_code_checks
from checks.engine.registry import CODE_RULES, HUMAN_RULES
from checks.engine.rule import applies
from core.domain import Channel, Market, Product

from .conftest import cc_terms, make_ctx


def test_rules_are_keyed_by_their_id() -> None:
    assert RULES
    for key, spec in RULES.items():
        assert key == spec.id


def test_rules_mapping_is_read_only() -> None:
    with pytest.raises(TypeError):
        RULES["x"] = next(iter(RULES.values()))  # type: ignore[index]


def test_rules_partition_into_code_and_human() -> None:
    assert {r.spec.id for r in CODE_RULES} == {r.id for r in RULES.values() if r.kind == "code"}
    assert {r.spec.id for r in HUMAN_RULES} == {r.id for r in RULES.values() if r.kind == "human"}
    assert len(CODE_RULES) + len(HUMAN_RULES) == len(RULES)


def test_ruleset_version_is_latest_effective_date() -> None:
    assert max(r.effective_from for r in RULES.values()) == RULESET_VERSION


def test_rule_specs_are_frozen() -> None:
    spec = next(iter(RULES.values()))
    with pytest.raises(FrozenInstanceError):
        spec.title = "x"  # type: ignore[misc]


def test_every_rule_has_citation_url_and_title() -> None:
    for spec in RULES.values():
        assert spec.title
        assert spec.citation
        assert spec.url.startswith("https://")
        assert spec.products


def test_context_rejects_terms_for_another_product() -> None:
    with pytest.raises(ValueError, match="terms"):
        make_ctx("x", product=Product.PERSONAL_LOAN, terms=cc_terms())


def test_span_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="span"):
        Span(5, 2)


def test_federal_rule_applies_even_with_no_markets() -> None:
    federal = RULES["claims.guaranteed"]
    assert applies(federal, make_ctx("x", markets=()))
    assert applies(federal, make_ctx("x", markets=(Market.CA,)))


def test_california_rule_needs_ca_market() -> None:
    ca = RULES["ca.license_disclosure"]
    assert applies(ca, make_ctx("x", markets=(Market.CA,)))
    assert applies(ca, make_ctx("x", markets=(Market.NATIONAL, Market.CA)))
    assert not applies(ca, make_ctx("x", markets=(Market.NATIONAL,)))


def test_channel_scoped_rule_only_on_its_channel() -> None:
    sms = RULES["sms.opt_out"]
    assert applies(sms, make_ctx("x", channel=Channel.SMS))
    assert not applies(sms, make_ctx("x", channel=Channel.EMAIL))


def test_product_scoped_rule_only_on_its_products() -> None:
    card = RULES["card.issuer_line"]
    assert applies(card, make_ctx("x", product=Product.CREDIT_CARD))
    assert not applies(card, make_ctx("x", product=Product.PERSONAL_LOAN))


def test_rule_not_yet_effective_does_not_apply() -> None:
    spec = RULES["human.reg_b_discouragement"]
    assert spec.effective_from == date(2026, 7, 21)
    assert not applies(spec, make_ctx("x", today=date(2026, 7, 20)))
    assert applies(spec, make_ctx("x", today=date(2026, 7, 21)))


def test_run_code_checks_returns_only_code_findings_with_rule_metadata() -> None:
    result = run_code_checks(make_ctx("Guaranteed approval on every loan."))
    assert result.findings
    for f in result.findings:
        spec = RULES[f.rule_id]
        assert spec.kind == "code"
        assert f.source == "code"
        assert f.severity == spec.severity
        assert f.citation == spec.citation


def test_human_checklist_is_human_sourced_and_unanchored() -> None:
    items = human_checklist(make_ctx("Any copy"))
    assert items
    for f in items:
        assert f.source == "human"
        assert f.span is None
        assert f.quote is None
        assert RULES[f.rule_id].kind == "human"


def test_context_is_frozen() -> None:
    ctx = make_ctx("x")
    assert isinstance(replace(ctx, text="y"), RuleContext)
    with pytest.raises(FrozenInstanceError):
        ctx.text = "y"  # type: ignore[misc]
