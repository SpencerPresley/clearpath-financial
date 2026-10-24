"""The model's only output channel: one tool, `report_findings`, and the parser for what comes back.

The schema carries findings and nothing else. No field can express approval, status, or a verdict on the item,
so there is nothing for injected copy to talk the model into setting. Unknown keys are ignored, unknown tools
are recorded and ignored, and malformed items are dropped one by one. None of that raises (spec §6.1).

The schema stays inside the strict tool-use subset: every object closed, every field required, no numeric
or string constraints, no `anyOf`. Turning on `strict` is then a flag, not a schema rewrite.
"""

from dataclasses import dataclass
from enum import StrEnum

from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, ValidationError

from checks.llm.rules import LLM_RULES

REPORT_TOOL_NAME = "report_findings"


class DropReason(StrEnum):
    MALFORMED = "malformed"  # an item or call that doesn't fit the schema
    NO_REPORT = "no_report"  # the model answered without calling report_findings
    UNKNOWN_TOOL = "unknown_tool"  # a call to a tool that doesn't exist; ignored
    UNKNOWN_RULE = "unknown_rule"
    NOT_APPLICABLE = "not_applicable"  # a real LLM rule that doesn't apply to this item
    EMPTY_QUOTE = "empty_quote"
    QUOTE_NOT_FOUND = "quote_not_found"
    AMBIGUOUS_QUOTE = "ambiguous_quote"
    DUPLICATE = "duplicate"  # same rule and span as an earlier LLM finding
    DUPLICATES_CODE = "duplicates_code"  # overlaps a code finding that reports the same problem


@dataclass(frozen=True)
class DroppedFinding:
    reason: DropReason
    rule_id: str | None
    quote: str | None
    detail: str


class RawFinding(BaseModel):
    """One finding as the model reported it, before any validation against the text."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    rule_id: str
    quote: str
    start: int
    end: int
    message: str
    suggested_fix: str = ""


@dataclass(frozen=True)
class ParsedOutput:
    items: tuple[RawFinding, ...]
    dropped: tuple[DroppedFinding, ...]
    # False when there is no usable report: prose instead of a tool call, an unparsable call, or no findings list.
    # Zero findings from a valid report is a clean result; zero findings from an invalid one is not.
    output_valid: bool


_STRING = "string"


def report_tool() -> dict[str, object]:
    """Anthropic-format tool definition (passed through `bind_tools` unchanged)."""
    item = {
        "type": "object",
        "properties": {
            "rule_id": {
                "type": _STRING,
                "enum": [rule.spec.id for rule in LLM_RULES],
                "description": "The applicable rule this finding is about.",
            },
            "quote": {
                "type": _STRING,
                "description": "The exact text from the ad copy that the finding is about, copied character for "
                "character.",
            },
            "start": {"type": "integer", "description": "Index in the ad copy where the quote starts."},
            "end": {"type": "integer", "description": "Index in the ad copy just past the end of the quote."},
            "message": {
                "type": _STRING,
                "description": "One sentence for the reviewer: what may be wrong and why.",
            },
            "suggested_fix": {
                "type": _STRING,
                "description": 'Replacement wording for the quote, or a concrete edit. "" if none.',
            },
        },
        "required": ["rule_id", "quote", "start", "end", "message", "suggested_fix"],
        "additionalProperties": False,
    }
    return {
        "name": REPORT_TOOL_NAME,
        "description": "Report the findings for this ad copy, once. An empty list means no findings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": item,
                    "description": "One entry per problem found. Empty if there are none.",
                },
            },
            "required": ["findings"],
            "additionalProperties": False,
        },
    }


def _str_or_none(item: object, key: str) -> str | None:
    if isinstance(item, dict):
        value = item.get(key)
        if isinstance(value, str):
            return value
    return None


def _validation_detail(error: ValidationError) -> str:
    first = error.errors()[0]
    location = ".".join(str(part) for part in first["loc"]) or "item"
    return f"{location}: {first['msg']}"


def _parse_items(findings: list[object]) -> tuple[list[RawFinding], list[DroppedFinding]]:
    items: list[RawFinding] = []
    dropped: list[DroppedFinding] = []
    for raw in findings:
        try:
            items.append(RawFinding.model_validate(raw))
        except ValidationError as error:
            dropped.append(
                DroppedFinding(
                    DropReason.MALFORMED, _str_or_none(raw, "rule_id"), _str_or_none(raw, "quote"),
                    _validation_detail(error),
                )
            )
    return items, dropped


def parse_report(message: AIMessage) -> ParsedOutput:
    items: list[RawFinding] = []
    dropped: list[DroppedFinding] = []
    reported = False
    broken = False
    for call in message.tool_calls:
        if call["name"] != REPORT_TOOL_NAME:
            dropped.append(DroppedFinding(DropReason.UNKNOWN_TOOL, None, None, call["name"]))
            continue
        findings = call["args"].get("findings")
        if not isinstance(findings, list):
            broken = True
            dropped.append(DroppedFinding(DropReason.MALFORMED, None, None, "findings is not a list"))
            continue
        reported = True
        call_items, call_dropped = _parse_items(findings)
        items.extend(call_items)
        dropped.extend(call_dropped)
    for invalid in message.invalid_tool_calls:
        broken = True
        detail = f"unparsable call to {invalid.get('name')}: {invalid.get('error')}"
        dropped.append(DroppedFinding(DropReason.MALFORMED, None, None, detail))
    if not message.tool_calls and not message.invalid_tool_calls:
        dropped.append(DroppedFinding(DropReason.NO_REPORT, None, None, "the model replied without a tool call"))
    return ParsedOutput(tuple(items), tuple(dropped), output_valid=reported and not broken)
