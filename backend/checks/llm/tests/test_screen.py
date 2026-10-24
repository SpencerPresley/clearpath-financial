from checks.engine import FindingDraft, Span, run_code_checks
from checks.engine.tests.conftest import make_ctx
from checks.llm.rules import LLM_RULES_BY_ID, applicable_rules
from checks.llm.schema import DropReason, RawFinding
from checks.llm.screen import Adjustment, screen
from checks.llm.tests.fakes import finding
from core.domain import Channel, FindingSource, PartnerType, Product, Severity

TEXT = "Free money for everyone! Free money, no hidden fees. Act now before rates go up."


def _screen(text, *items, ctx=None, code_findings=()):
    ctx = ctx or make_ctx(text)
    raw = [RawFinding.model_validate(i) for i in items]
    return screen(ctx, raw, rules=applicable_rules(ctx), code_findings=code_findings)


def test_kept_finding_is_llm_source_with_rule_citation_and_severity():
    result = _screen(TEXT, finding(TEXT, "llm.net_impression", "no hidden fees"))
    (kept,) = result.findings
    rule = LLM_RULES_BY_ID["llm.net_impression"]
    start = TEXT.index("no hidden fees")
    assert kept == FindingDraft(
        rule_id="llm.net_impression",
        source=FindingSource.LLM,
        severity=Severity.WARNING,
        message="This claim may give a misleading impression of the offer.",
        citation=rule.spec.citation,
        suggested_fix=None,
        span=Span(start, start + 14),
        quote="no hidden fees",
    )
    assert result.dropped == ()
    assert result.adjustments == ()


def test_unknown_rule_dropped():
    result = _screen(TEXT, finding(TEXT, "pricing.terms_available", "no hidden fees"))
    assert result.findings == ()
    assert [(d.reason, d.rule_id) for d in result.dropped] == [(DropReason.UNKNOWN_RULE, "pricing.terms_available")]


def test_inapplicable_rule_dropped():
    # mortgage_comparison on a personal loan; material_connection on first-party content
    result = _screen(
        TEXT,
        finding(TEXT, "llm.mortgage_comparison", "Free money for everyone!"),
        finding(TEXT, "llm.material_connection", "no hidden fees"),
    )
    assert result.findings == ()
    assert [d.reason for d in result.dropped] == [DropReason.NOT_APPLICABLE] * 2


def test_span_rejections_dropped_with_reason():
    result = _screen(
        TEXT,
        finding(TEXT, "llm.net_impression", "guaranteed cash"),
        finding(TEXT, "llm.net_impression", "Free money", offset_error=3),
        finding(TEXT, "llm.net_impression", "", start=0, end=0),
    )
    assert result.findings == ()
    assert [d.reason for d in result.dropped] == [
        DropReason.QUOTE_NOT_FOUND,
        DropReason.AMBIGUOUS_QUOTE,
        DropReason.EMPTY_QUOTE,
    ]
    assert result.dropped[0].quote == "guaranteed cash"


def test_reanchored_finding_is_kept_and_recorded():
    result = _screen(TEXT, finding(TEXT, "llm.pressure_tactics", "Act now before rates go up.", offset_error=-7))
    (kept,) = result.findings
    start = TEXT.index("Act now")
    assert kept.span == Span(start, len(TEXT))
    assert kept.quote == TEXT[start:]
    assert result.adjustments == (
        Adjustment(
            kind="reanchored",
            rule_id="llm.pressure_tactics",
            quote="Act now before rates go up.",
            detail=f"model said [{start - 7}, {len(TEXT) - 7}), found at [{start}, {len(TEXT)})",
        ),
    )


def test_repeated_quote_at_correct_offsets_kept():
    second = TEXT.index("Free money,")
    item = finding(TEXT, "llm.net_impression", "Free money", start=second, end=second + 10)
    (kept,) = _screen(TEXT, item).findings
    assert kept.span == Span(second, second + 10)


def test_duplicate_llm_finding_dropped():
    item = finding(TEXT, "llm.net_impression", "no hidden fees")
    result = _screen(TEXT, item, item)
    assert len(result.findings) == 1
    assert [d.reason for d in result.dropped] == [DropReason.DUPLICATE]


def test_same_span_different_rules_both_kept():
    result = _screen(
        TEXT,
        finding(TEXT, "llm.net_impression", "Act now before rates go up."),
        finding(TEXT, "llm.pressure_tactics", "Act now before rates go up."),
    )
    assert [f.rule_id for f in result.findings] == ["llm.net_impression", "llm.pressure_tactics"]


def test_overlapping_counterpart_code_finding_drops_duplicate():
    text = "Personal loans as low as 7.49% APR. Apply today."
    ctx = make_ctx(text)
    code = run_code_checks(ctx).findings
    assert "pricing.creditworthiness_qualifier" in {f.rule_id for f in code}
    result = _screen(
        text, finding(text, "llm.creditworthiness_qualifier", "as low as 7.49% APR"), ctx=ctx, code_findings=code
    )
    assert result.findings == ()
    assert [(d.reason, d.detail) for d in result.dropped] == [
        (DropReason.DUPLICATES_CODE, "pricing.creditworthiness_qualifier")
    ]


def test_non_overlapping_counterpart_code_finding_does_not_drop():
    text = "Personal loans as low as 7.49% APR. Fast funding, free money!"
    ctx = make_ctx(text)
    code = (
        FindingDraft(
            "claims.guaranteed", FindingSource.CODE, Severity.BLOCKING, "m", "c", None, Span(0, 14), text[:14]
        ),
    )
    result = _screen(text, finding(text, "llm.net_impression", "free money!"), ctx=ctx, code_findings=code)
    assert len(result.findings) == 1


def test_overlapping_unrelated_code_finding_does_not_drop():
    text = "Personal loans as low as 7.49% APR."
    ctx = make_ctx(text)
    code = run_code_checks(ctx).findings
    assert "pricing.as_low_as_range" in {f.rule_id for f in code}  # overlaps, but reports a different problem
    result = _screen(text, finding(text, "llm.net_impression", "as low as 7.49% APR"), ctx=ctx, code_findings=code)
    assert len(result.findings) == 1


def test_spanless_counterpart_code_finding_drops_any_finding_of_that_rule():
    text = "Our pick: ClearPath personal loans. We love their fast funding!"
    ctx = make_ctx(text, channel=Channel.AFFILIATE_PAGE, partner_type=PartnerType.AFFILIATE)
    code = run_code_checks(ctx).findings
    assert any(f.rule_id == "endorsement.material_connection" and f.span is None for f in code)
    result = _screen(
        text, finding(text, "llm.material_connection", "We love their fast funding!"), ctx=ctx, code_findings=code
    )
    assert [d.reason for d in result.dropped] == [DropReason.DUPLICATES_CODE]


def test_banned_wording_replaced_by_default_message():
    item = finding(TEXT, "llm.net_impression", "no hidden fees", message="This is a UDAAP violation and illegal.")
    result = _screen(TEXT, item)
    (kept,) = result.findings
    assert kept.message == LLM_RULES_BY_ID["llm.net_impression"].default_message
    assert [a.kind for a in result.adjustments] == ["reworded"]


def test_non_compliant_and_blank_messages_replaced():
    result = _screen(
        TEXT,
        finding(TEXT, "llm.net_impression", "no hidden fees", message="Non-compliant claim."),
        finding(TEXT, "llm.pressure_tactics", "Act now before rates go up.", message="   "),
    )
    assert [f.message for f in result.findings] == [
        LLM_RULES_BY_ID["llm.net_impression"].default_message,
        LLM_RULES_BY_ID["llm.pressure_tactics"].default_message,
    ]


def test_suggested_fix_kept_and_stripped():
    item = finding(TEXT, "llm.net_impression", "no hidden fees", suggested_fix="  Origination fee 0%\N{EN DASH}8%.  ")
    (kept,) = _screen(TEXT, item).findings
    assert kept.suggested_fix == "Origination fee 0%\N{EN DASH}8%."


def test_findings_sorted_by_position_then_rule():
    result = _screen(
        TEXT,
        finding(TEXT, "llm.pressure_tactics", "Act now before rates go up."),
        finding(TEXT, "llm.net_impression", "no hidden fees"),
        finding(TEXT, "llm.net_impression", "Free money for everyone!"),
    )
    assert [f.quote for f in result.findings] == [
        "Free money for everyone!",
        "no hidden fees",
        TEXT[TEXT.index("Act") :],
    ]


def test_mortgage_rule_kept_on_mortgage_item():
    text = "Refinance and save $300 a month."
    ctx = make_ctx(text, product=Product.MORTGAGE_PREQUAL, terms=None)
    (kept,) = _screen(text, finding(text, "llm.mortgage_comparison", "save $300 a month"), ctx=ctx).findings
    assert kept.rule_id == "llm.mortgage_comparison"
