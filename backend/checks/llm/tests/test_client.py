"""The request ChatAnthropic would send, built offline with `_get_request_payload` (no network).

This pins wire-level facts the docs make load-bearing: Haiku 5.5 returns a 400 for any temperature other than
1, so none is sent; the system block keeps its cache breakpoint; the tool and tool_choice reach the payload.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import RunnableBinding

from checks.engine.tests.conftest import make_ctx
from checks.llm.client import (
    DEFAULT_MODEL,
    MAX_RETRIES,
    MAX_TOKENS,
    MAX_TOKENS_WITH_THINKING,
    TIMEOUT_SECONDS,
    forces_tool_choice,
    get_review_model,
)
from checks.llm.prompt import item_message, system_message
from checks.llm.rules import applicable_rules
from checks.llm.schema import REPORT_TOOL_NAME, report_tool


def _payload(model: ChatAnthropic) -> dict:
    ctx = make_ctx("Personal loans as low as 7.49% APR.")
    bound = model.bind_tools([report_tool()], tool_choice=REPORT_TOOL_NAME)
    assert isinstance(bound, RunnableBinding)
    messages = [system_message(), item_message(ctx, applicable_rules(ctx), ())]
    return model._get_request_payload(messages, **bound.kwargs)  # noqa: SLF001


def test_defaults():
    model = get_review_model(api_key="test-key")
    assert isinstance(model, ChatAnthropic)
    assert model.model == DEFAULT_MODEL == "claude-haiku-5-5"
    assert model.max_tokens == MAX_TOKENS == 2048
    assert model.max_retries == MAX_RETRIES == 3
    assert model.default_request_timeout == TIMEOUT_SECONDS == 60.0
    assert model.temperature is None
    assert model.anthropic_api_key.get_secret_value() == "test-key"


def test_model_name_is_a_parameter():
    assert get_review_model("claude-sonnet-5", api_key="k").model == "claude-sonnet-5"


def test_models_that_think_before_the_tool_get_a_larger_cap():
    assert get_review_model("claude-opus-5-5", api_key="k").max_tokens == MAX_TOKENS_WITH_THINKING
    assert get_review_model("claude-haiku-5-5", api_key="k").max_tokens == MAX_TOKENS


def test_payload_has_no_sampling_parameters():
    payload = _payload(get_review_model(api_key="k"))
    for key in ("temperature", "top_p", "top_k", "thinking"):
        assert key not in payload


def test_payload_keeps_cache_breakpoint_on_system_block():
    payload = _payload(get_review_model(api_key="k"))
    system = payload["system"]
    assert isinstance(system, list)
    assert system[-1]["cache_control"] == {"type": "ephemeral"}
    assert system[-1]["text"] == system_message().content[-1]["text"]  # type: ignore[index]


def test_payload_forces_the_report_tool():
    payload = _payload(get_review_model(api_key="k"))
    assert payload["max_tokens"] == MAX_TOKENS
    assert payload["tools"] == [report_tool()]
    assert payload["tool_choice"] == {"type": "tool", "name": REPORT_TOOL_NAME}
    (user,) = payload["messages"]
    assert user["role"] == "user"


def test_forced_tool_choice_support():
    assert forces_tool_choice("claude-haiku-5-5")
    assert forces_tool_choice("claude-sonnet-5")
    for name in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-mythos-5-1-20261001"):
        assert not forces_tool_choice(name)
