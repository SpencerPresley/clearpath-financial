import re

from checks.engine import RULES
from checks.engine.tests.conftest import make_ctx
from checks.llm.rules import LLM_RULES, LLM_RULES_BY_ID, LLM_RULESET_VERSION, applicable_rules
from core.domain import Channel, FindingSource, Market, PartnerType, Product, Severity

BANNED = re.compile(r"violat|non-?\s?compliant|illegal|unlawful", re.IGNORECASE)


def _ids(ctx) -> set[str]:
    return {r.spec.id for r in applicable_rules(ctx)}


def test_rule_ids_unique_and_prefixed():
    ids = [r.spec.id for r in LLM_RULES]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("llm.") for i in ids)
    assert set(LLM_RULES_BY_ID) == set(ids)


def test_every_rule_is_llm_kind_warning_with_citation_and_url():
    for rule in LLM_RULES:
        assert rule.spec.kind == "llm"
        assert rule.spec.severity == Severity.WARNING
        assert rule.spec.citation
        assert rule.spec.url.startswith("https://")
        assert rule.guidance.strip()
        assert rule.spec.markets == frozenset(Market)


def test_ruleset_version_is_max_effective_from():
    assert max(r.spec.effective_from for r in LLM_RULES) == LLM_RULESET_VERSION


def test_material_connection_needs_partner_or_affiliate_channel():
    first_party = make_ctx("x", channel=Channel.PAID_SOCIAL)
    influencer = make_ctx("x", channel=Channel.PAID_SOCIAL, partner_type=PartnerType.INFLUENCER)
    affiliate_page = make_ctx("x", channel=Channel.AFFILIATE_PAGE)
    assert "llm.material_connection" not in _ids(first_party)
    assert "llm.material_connection" in _ids(influencer)
    assert "llm.material_connection" in _ids(affiliate_page)


def test_mortgage_comparison_only_for_mortgage():
    assert "llm.mortgage_comparison" in _ids(make_ctx("x", product=Product.MORTGAGE_PREQUAL, terms=None))
    assert "llm.mortgage_comparison" not in _ids(make_ctx("x", product=Product.PERSONAL_LOAN))
    assert "llm.mortgage_comparison" not in _ids(make_ctx("x", product=Product.CREDIT_CARD))


def test_reg_b_rule_not_applicable_before_its_effective_date():
    from datetime import date

    assert "llm.discouraging_statement" not in _ids(make_ctx("x", today=date(2026, 7, 20)))
    assert "llm.discouraging_statement" in _ids(make_ctx("x", today=date(2026, 7, 21)))


def test_counterparts_are_real_engine_rule_ids():
    for rule in LLM_RULES:
        assert rule.code_counterparts <= set(RULES), rule.spec.id


def test_default_messages_use_suggestion_register():
    for rule in LLM_RULES:
        assert rule.default_message
        assert not BANNED.search(rule.default_message)
        assert not BANNED.search(rule.spec.title)


def test_llm_source_exists_in_domain():
    # The finding source the layer emits; guards against a rename in core.domain.
    assert FindingSource.LLM.value == "llm"
