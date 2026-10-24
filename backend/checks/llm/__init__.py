"""LLM pre-review of marketing copy. Pure Python; no Django.

`review_copy` asks the model to judge the `LLM_RULES` that apply to an item. It returns span-validated
`FindingDraft`s (source=LLM), plus what was dropped and why, token usage, and latency. `get_review_model` builds the
production model. Nothing the model returns can approve anything or change a status.
"""

from checks.llm.client import DEFAULT_MODEL, get_review_model
from checks.llm.prompt import PROMPT_VERSION
from checks.llm.review import LlmReviewResult, LlmUnavailable, TokenUsage, review_copy
from checks.llm.rules import LLM_RULES, LLM_RULES_BY_ID, LLM_RULESET_VERSION, LlmRule, applicable_rules
from checks.llm.schema import DroppedFinding, DropReason
from checks.llm.screen import Adjustment
from checks.llm.spans import Anchor, SpanRejection, anchor_quote

__all__ = [
    "DEFAULT_MODEL",
    "LLM_RULES",
    "LLM_RULESET_VERSION",
    "LLM_RULES_BY_ID",
    "PROMPT_VERSION",
    "Adjustment",
    "Anchor",
    "DropReason",
    "DroppedFinding",
    "LlmReviewResult",
    "LlmRule",
    "LlmUnavailable",
    "SpanRejection",
    "TokenUsage",
    "anchor_quote",
    "applicable_rules",
    "get_review_model",
    "review_copy",
]
