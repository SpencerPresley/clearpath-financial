"""A scripted chat model for review_copy tests.

`GenericFakeChatModel` doesn't implement `bind_tools` (LangChain unit-testing docs), so this subclass records
what was bound and every request, and returns itself.
"""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.tool import tool_call
from langchain_core.outputs import ChatResult
from pydantic import Field

from checks.llm.schema import REPORT_TOOL_NAME


class FakeToolModel(GenericFakeChatModel):
    model: str = "claude-haiku-5-5"
    bound_tools: list[Any] = Field(default_factory=list)
    bound_kwargs: dict[str, Any] = Field(default_factory=dict)
    requests: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeToolModel":  # type: ignore[override]
        self.bound_tools = list(tools)
        self.bound_kwargs = dict(kwargs)
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.requests.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class RaisingModel(FakeToolModel):
    error: Exception

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.requests.append(list(messages))
        raise self.error


def report(*findings: dict[str, object], stop_reason: str = "tool_use", **usage: int) -> AIMessage:
    """An AIMessage shaped like ChatAnthropic's reply to a forced report_findings call."""
    return AIMessage(
        content="",
        tool_calls=[tool_call(name=REPORT_TOOL_NAME, args={"findings": list(findings)}, id="toolu_1")],
        response_metadata={"model_name": "claude-haiku-5-5-20261001", "stop_reason": stop_reason},
        usage_metadata={
            "input_tokens": usage.get("input_tokens", 1800),
            "output_tokens": usage.get("output_tokens", 120),
            "total_tokens": usage.get("input_tokens", 1800) + usage.get("output_tokens", 120),
            "input_token_details": {
                "cache_read": usage.get("cache_read", 1500),
                "cache_creation": usage.get("cache_creation", 0),
            },
        },
    )


def fake(*responses: AIMessage | str) -> FakeToolModel:
    return FakeToolModel(messages=iter(responses))


def finding(text: str, rule_id: str, quote: str, *, offset_error: int = 0, **overrides: object) -> dict[str, object]:
    """A model finding for `quote` in `text`, with its offsets shifted by `offset_error` (models miscount)."""
    start = text.find(quote)
    start = max(start, 0) + offset_error
    item: dict[str, object] = {
        "rule_id": rule_id,
        "quote": quote,
        "start": start,
        "end": start + len(quote),
        "message": "This claim may give a misleading impression of the offer.",
        "suggested_fix": "",
    }
    item.update(overrides)
    return item
