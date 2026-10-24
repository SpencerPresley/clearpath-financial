import dataclasses
from typing import cast

import anthropic
import httpx2
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.ai import InputTokenDetails
from langchain_core.messages.tool import invalid_tool_call, tool_call

from checks.engine import run_code_checks
from checks.engine.tests.conftest import make_ctx
from checks.llm import LlmReviewResult, LlmUnavailable, TokenUsage, review_copy
from checks.llm.prompt import PROMPT_VERSION, copy_tag
from checks.llm.rules import LLM_RULESET_VERSION
from checks.llm.schema import REPORT_TOOL_NAME, DropReason, report_tool
from checks.llm.tests.fakes import RaisingModel, fake, finding, report
from core.domain import FindingSource, Product

TEXT = "ClearPath personal loans: free money in minutes! Act now before rates go up. Rates as low as 7.49% APR."
STATUS_LIKE = ("status", "approv", "decision", "outcome", "verdict")


def _ctx(text: str = TEXT, **kwargs):
    return make_ctx(text, **kwargs)


def _review(model, ctx=None):
    ctx = ctx or _ctx()
    return review_copy(ctx, code_findings=run_code_checks(ctx).findings, model=model)


def test_happy_path():
    model = fake(
        report(
            finding(TEXT, "llm.net_impression", "free money in minutes!"),
            finding(TEXT, "llm.pressure_tactics", "Act now before rates go up."),
            input_tokens=2000,
            output_tokens=150,
            cache_read=1600,
            cache_creation=0,
        )
    )
    result = _review(model)
    assert isinstance(result, LlmReviewResult)
    assert [f.rule_id for f in result.findings] == ["llm.net_impression", "llm.pressure_tactics"]
    assert all(f.source is FindingSource.LLM for f in result.findings)
    assert all(f.quote == TEXT[f.span.start : f.span.end] for f in result.findings if f.span)
    assert result.dropped == ()
    assert result.output_valid
    assert result.stop_reason == "tool_use"
    assert result.usage == TokenUsage(
        input_tokens=2000, output_tokens=150, cache_read_tokens=1600, cache_creation_tokens=0
    )
    assert result.model_name == "claude-haiku-5-5-20261001"
    assert result.latency_ms >= 0
    assert result.prompt_version == PROMPT_VERSION
    assert result.ruleset_version == LLM_RULESET_VERSION


def test_request_shape():
    model = fake(report())
    ctx = _ctx()
    _review(model, ctx)
    assert model.bound_tools == [report_tool()]
    assert model.bound_kwargs == {"tool_choice": REPORT_TOOL_NAME}
    (request,) = model.requests
    system, human = request
    assert isinstance(system, SystemMessage)
    assert isinstance(human, HumanMessage)
    assert isinstance(human.content, str)
    assert f"<{copy_tag(TEXT)}>\n{TEXT}\n</{copy_tag(TEXT)}>" in human.content
    assert TEXT not in str(system.content)


@pytest.mark.parametrize(
    "model_name", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-mythos-5-1"]
)
def test_models_without_forced_tool_choice_get_auto(model_name):
    model = fake(report())
    model.model = model_name
    _review(model)
    assert model.bound_kwargs == {"tool_choice": "auto"}


def test_malformed_output_is_dropped_and_counted_not_raised():
    model = fake(
        report(
            {"rule_id": "llm.net_impression", "quote": "free money"},  # missing fields
            "not an object",  # type: ignore[arg-type]
            finding(TEXT, "llm.pressure_tactics", "Act now before rates go up."),
        )
    )
    result = _review(model)
    assert [f.rule_id for f in result.findings] == ["llm.pressure_tactics"]
    assert [d.reason for d in result.dropped] == [DropReason.MALFORMED, DropReason.MALFORMED]
    assert result.output_valid


def test_hallucinated_span_dropped():
    model = fake(
        report(
            finding(TEXT, "llm.net_impression", "guaranteed approval for everyone"),  # not in the copy
            finding(TEXT, "llm.net_impression", "free money in minutes!", offset_error=11),  # wrong offsets, unique
        )
    )
    result = _review(model)
    assert [d.reason for d in result.dropped] == [DropReason.QUOTE_NOT_FOUND]
    (kept,) = result.findings
    assert kept.quote == "free money in minutes!"
    assert [a.kind for a in result.adjustments] == ["reanchored"]


def test_status_setting_tool_call_is_ignored():
    message = AIMessage(
        content="",
        tool_calls=[
            tool_call(name="set_status", args={"item": "CP-1042", "status": "approved"}, id="t1"),
            tool_call(
                name=REPORT_TOOL_NAME,
                args={"findings": [], "status": "approved", "approved": True, "decision": "approve"},
                id="t2",
            ),
        ],
        response_metadata={"stop_reason": "tool_use"},
    )
    result = _review(fake(message))
    assert result.findings == ()
    assert [(d.reason, d.detail) for d in result.dropped] == [(DropReason.UNKNOWN_TOOL, "set_status")]
    fields = {f.name for f in dataclasses.fields(result)}
    assert not [f for f in fields if any(s in f for s in STATUS_LIKE)]


def test_prose_reply_is_invalid_output():
    result = _review(
        fake(AIMessage(content="Looks compliant. Approved.", response_metadata={"stop_reason": "end_turn"}))
    )
    assert result.findings == ()
    assert not result.output_valid
    assert [d.reason for d in result.dropped] == [DropReason.NO_REPORT]


def test_truncated_tool_call_is_invalid_output():
    message = AIMessage(
        content="",
        invalid_tool_calls=[invalid_tool_call(name=REPORT_TOOL_NAME, args='{"findings": [{"rule', id="t", error="EOF")],
        response_metadata={"stop_reason": "max_tokens"},
    )
    result = _review(fake(message))
    assert not result.output_valid
    assert result.stop_reason == "max_tokens"
    assert [d.reason for d in result.dropped] == [DropReason.MALFORMED]


def test_max_tokens_stop_marks_output_invalid_even_if_parsed():
    result = _review(
        fake(report(finding(TEXT, "llm.net_impression", "free money in minutes!"), stop_reason="max_tokens"))
    )
    assert len(result.findings) == 1
    assert not result.output_valid


def test_missing_usage_is_zero():
    message = AIMessage(content="", tool_calls=[tool_call(name=REPORT_TOOL_NAME, args={"findings": []}, id="t")])
    result = _review(fake(message))
    assert result.usage == TokenUsage()
    assert result.model_name == "claude-haiku-5-5"  # falls back to the configured model
    assert result.stop_reason is None


def test_cache_creation_uses_ttl_split_when_present():
    message = report()
    assert message.usage_metadata is not None
    # The shape langchain-anthropic produces: undeclared TTL keys, generic cache_creation zeroed.
    details = {"cache_read": 0, "cache_creation": 0, "ephemeral_5m_input_tokens": 1700, "ephemeral_1h_input_tokens": 0}
    message.usage_metadata["input_token_details"] = cast("InputTokenDetails", details)
    assert TokenUsage.from_message(message).cache_creation_tokens == 1700


def test_no_applicable_rules_skips_the_model():
    model = fake()  # an empty script: any call would raise StopIteration
    ctx = _ctx(today=__import__("datetime").date(2016, 1, 1))  # before every rule's effective date
    result = review_copy(ctx, code_findings=(), model=model)
    assert model.requests == []
    assert result.output_valid
    assert result.findings == ()


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(status: int) -> anthropic.APIStatusError:
    return anthropic.APIStatusError("boom", response=httpx2.Response(status, request=_request()), body=None)


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (anthropic.APIConnectionError(request=_request()), True),
        (anthropic.APITimeoutError(request=_request()), True),
        (_status_error(429), True),
        (_status_error(529), True),
        (_status_error(500), True),
        (_status_error(408), True),
        (_status_error(400), False),
        (_status_error(401), False),
    ],
    ids=["connection", "timeout", "429", "529", "500", "408", "400", "401"],
)
def test_provider_errors_become_llm_unavailable(error, retryable):
    model = RaisingModel(messages=iter(()), error=error)
    with pytest.raises(LlmUnavailable) as info:
        _review(model)
    assert info.value.retryable is retryable
    assert info.value.__cause__ is error


def test_programming_errors_are_not_wrapped():
    model = RaisingModel(messages=iter(()), error=KeyError("bug"))
    with pytest.raises(KeyError):
        _review(model)


def test_mortgage_item_gets_mortgage_rule():
    text = "Refinance with ClearPath and save $300 a month!"
    ctx = make_ctx(text, product=Product.MORTGAGE_PREQUAL, terms=None)
    result = review_copy(
        ctx, code_findings=(), model=fake(report(finding(text, "llm.mortgage_comparison", "save $300 a month")))
    )
    assert [f.rule_id for f in result.findings] == ["llm.mortgage_comparison"]
