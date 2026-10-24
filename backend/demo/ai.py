"""A scripted stand-in for the AI pre-review model, so the seed is deterministic and makes no live calls.

The seed hands these to `checks.prereview.attempt` through its `model_factory` parameter, so a scripted result goes
through the same parsing, span validation and code-duplicate screening as a real one, and lands through the same
`complete` / `requeue` / `fail` transitions. The model reports its name as `demo-seed`, which is what the CheckRun
and the LLM_CHECK_SUCCEEDED event record: nobody should mistake a seeded result for a live one.

`GenericFakeChatModel` has no `bind_tools` (LangChain's unit-testing docs), so this subclass returns itself.
"""

from collections.abc import Sequence
from typing import Any, Final

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.tool import tool_call
from langchain_core.outputs import ChatResult

from checks.llm import LlmUnavailable
from checks.llm.schema import REPORT_TOOL_NAME
from demo.story import AiFinding

MODEL_NAME: Final = "demo-seed"


class ScriptedReviewModel(GenericFakeChatModel):
    model: str = MODEL_NAME

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedReviewModel":  # noqa: ANN401, ARG002  # LangChain's signature
        return self

    @classmethod
    def reporting(cls, text: str, findings: Sequence[AiFinding]) -> "ScriptedReviewModel":
        """A model whose one answer is a report_findings call with `findings`, anchored at their quotes in `text`."""
        reported = []
        for finding in findings:
            start = text.find(finding.quote)
            reported.append(
                {
                    "rule_id": finding.rule_id,
                    "quote": finding.quote,
                    "start": start,
                    "end": start + len(finding.quote),
                    "message": finding.message,
                    "suggested_fix": finding.suggested_fix,
                }
            )
        message = AIMessage(
            content="",
            tool_calls=[tool_call(name=REPORT_TOOL_NAME, args={"findings": reported}, id="toolu_demo")],
            response_metadata={"model_name": MODEL_NAME, "stop_reason": "tool_use"},
        )
        return cls(messages=iter([message]))


class OverloadedModel(ScriptedReviewModel):
    """The provider answers 529 (overloaded) on every call; the check retries on its backoff, then fails."""

    def _generate(  # LangChain's hook
        self,
        messages: list[BaseMessage],  # noqa: ARG002  # LangChain's signature
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: Any = None,  # noqa: ANN401, ARG002
        **kwargs: Any,  # noqa: ANN401, ARG002
    ) -> ChatResult:
        raise LlmUnavailable("The model provider returned 529.", retryable=True)
