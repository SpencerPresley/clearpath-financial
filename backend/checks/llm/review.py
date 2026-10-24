"""`review_copy`: one model call, then parse and screen. The one integration boundary with the provider.

Errors (spec §6.1):
- A provider or network failure raises `LlmUnavailable`. That happens only after the client's own bounded
  retries (see `client.py`), and the exception says whether trying again later can help.
- Anything wrong with the model's output is a value. It shows up as dropped findings, and `output_valid=False`
  when there is no usable report.
"""

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import anthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage

from checks.engine.types import FindingDraft, RuleContext
from checks.llm.client import forces_tool_choice
from checks.llm.prompt import PROMPT_VERSION, item_message, system_message
from checks.llm.rules import LLM_RULESET_VERSION, applicable_rules
from checks.llm.schema import REPORT_TOOL_NAME, DroppedFinding, parse_report, report_tool
from checks.llm.screen import Adjustment, screen

# Mirrors the Anthropic SDK's own retry policy (anthropic/_base_client.py `_should_retry`).
_RETRYABLE_STATUS = frozenset({408, 409, 429})


class LlmUnavailable(Exception):  # noqa: N818 - a domain outcome, named for what happened
    """The model provider couldn't be reached or refused the request, after the client's retries."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def _count(details: Mapping[str, object], key: str) -> int:
    value = details.get(key)
    return value if isinstance(value, int) else 0


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0  # every input token, cached ones included (LangChain's convention)
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @classmethod
    def from_message(cls, message: AIMessage) -> "TokenUsage":
        usage = message.usage_metadata
        if usage is None:
            return cls()
        # langchain-anthropic adds the per-TTL cache-write split under keys InputTokenDetails doesn't declare. When
        # it's present the generic "cache_creation" is zeroed to avoid double counting, so prefer the split.
        details: Mapping[str, object] = dict(usage.get("input_token_details") or {})
        ttl_split = _count(details, "ephemeral_5m_input_tokens") + _count(details, "ephemeral_1h_input_tokens")
        return cls(
            input_tokens=usage.get("input_tokens") or 0,
            output_tokens=usage.get("output_tokens") or 0,
            cache_read_tokens=_count(details, "cache_read"),
            cache_creation_tokens=ttl_split or _count(details, "cache_creation"),
        )

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_creation_tokens + other.cache_creation_tokens,
        )


@dataclass(frozen=True)
class LlmReviewResult:
    """What one pre-review produced. There is deliberately no status or verdict here: only findings."""

    findings: tuple[FindingDraft, ...]  # source=LLM, span-validated
    dropped: tuple[DroppedFinding, ...]
    adjustments: tuple[Adjustment, ...]  # re-anchored spans, reworded messages
    usage: TokenUsage
    model_name: str
    latency_ms: int
    # False when the model gave no usable report (prose, unparsable or truncated output). Zero findings with
    # output_valid=False is not a clean pass; treat it as a failed check.
    output_valid: bool
    stop_reason: str | None
    prompt_version: str
    ruleset_version: date


def _configured_name(model: BaseChatModel) -> str:
    name = getattr(model, "model", None) or getattr(model, "model_name", None)
    return name if isinstance(name, str) else type(model).__name__


def _invoke(model: BaseChatModel, messages: list[BaseMessage]) -> AIMessage:
    forced = forces_tool_choice(_configured_name(model))
    bound = model.bind_tools([report_tool(strict=not forced)], tool_choice=REPORT_TOOL_NAME if forced else "auto")
    try:
        return bound.invoke(messages)
    except anthropic.APIConnectionError as error:  # includes timeouts
        raise LlmUnavailable("Couldn't reach the model provider.", retryable=True) from error
    except anthropic.APIStatusError as error:
        retryable = error.status_code in _RETRYABLE_STATUS or error.status_code >= 500  # noqa: PLR2004
        raise LlmUnavailable(f"The model provider returned {error.status_code}.", retryable=retryable) from error
    except anthropic.APIError as error:
        raise LlmUnavailable("The model provider's response couldn't be read.", retryable=False) from error


def review_copy(
    ctx: RuleContext,
    *,
    code_findings: Sequence[FindingDraft],
    model: BaseChatModel,
) -> LlmReviewResult:
    rules = applicable_rules(ctx)
    if not rules:
        return LlmReviewResult(
            findings=(),
            dropped=(),
            adjustments=(),
            usage=TokenUsage(),
            model_name=_configured_name(model),
            latency_ms=0,
            output_valid=True,
            stop_reason=None,
            prompt_version=PROMPT_VERSION,
            ruleset_version=LLM_RULESET_VERSION,
        )
    started = time.perf_counter()
    response = _invoke(model, [system_message(), item_message(ctx, rules, code_findings)])
    latency_ms = round((time.perf_counter() - started) * 1000)

    parsed = parse_report(response)
    screened = screen(ctx, parsed.items, rules=rules, code_findings=code_findings)
    stop_reason = response.response_metadata.get("stop_reason")
    model_name = response.response_metadata.get("model_name") or _configured_name(model)
    return LlmReviewResult(
        findings=screened.findings,
        dropped=parsed.dropped + screened.dropped,
        adjustments=screened.adjustments,
        usage=TokenUsage.from_message(response),
        model_name=model_name,
        latency_ms=latency_ms,
        output_valid=parsed.output_valid and stop_reason != "max_tokens",
        stop_reason=stop_reason,
        prompt_version=PROMPT_VERSION,
        ruleset_version=LLM_RULESET_VERSION,
    )
