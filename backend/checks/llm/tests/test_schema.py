import re
from collections.abc import Iterator

from langchain_core.messages import AIMessage
from langchain_core.messages.tool import invalid_tool_call, tool_call

from checks.llm.rules import LLM_RULES
from checks.llm.schema import REPORT_TOOL_NAME, DropReason, RawFinding, parse_report, report_tool

STATUS_LIKE = re.compile(r"status|approv|decision|state|outcome|pass|verdict|clear", re.IGNORECASE)


def _item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "rule_id": "llm.net_impression",
        "quote": "free money",
        "start": 0,
        "end": 10,
        "message": "This may read as a gift rather than a loan.",
        "suggested_fix": "Low-rate personal loans",
    }
    item.update(overrides)
    return item


def _report(*items: dict[str, object], **extra: object) -> AIMessage:
    args = {"findings": list(items), **extra}
    return AIMessage(content="", tool_calls=[tool_call(name=REPORT_TOOL_NAME, args=args, id="call_1")])


def _objects(node: object) -> Iterator[dict]:
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _objects(value)


def _property_names(node: object) -> Iterator[str]:
    for obj in _objects(node):
        yield from obj.get("properties", {})


def test_schema_has_no_status_or_approval_field():
    names = list(_property_names(report_tool()["input_schema"]))
    assert names, "schema has properties"
    assert not [n for n in names if STATUS_LIKE.search(n)]


def test_schema_is_strict_compatible():
    schema = report_tool()["input_schema"]
    for obj in _objects(schema):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    text = repr(schema)
    for unsupported in ("anyOf", "minimum", "maximum", "minLength", "maxLength", "maxItems", "$ref"):
        assert unsupported not in text


def test_rule_id_enum_is_all_llm_rules():
    item_props = report_tool()["input_schema"]["properties"]["findings"]["items"]["properties"]
    assert item_props["rule_id"]["enum"] == [r.spec.id for r in LLM_RULES]


def test_tool_is_anthropic_format_with_descriptions():
    tool = report_tool()
    assert tool["name"] == REPORT_TOOL_NAME
    assert tool["description"]
    item_props = tool["input_schema"]["properties"]["findings"]["items"]["properties"]
    assert all(p.get("description") for p in item_props.values())


def test_parses_valid_call():
    parsed = parse_report(_report(_item()))
    assert parsed.output_valid
    assert parsed.items == (RawFinding(**_item()),)
    assert parsed.dropped == ()


def test_empty_findings_list_is_valid_output():
    parsed = parse_report(_report())
    assert parsed.output_valid
    assert parsed.items == ()


def test_bad_item_dropped_others_kept():
    good = _item()
    missing_quote = _item()
    del missing_quote["quote"]
    wrong_type = _item(start="twelve")
    not_an_object = "llm.net_impression free money"
    parsed = parse_report(_report(good, missing_quote, wrong_type, not_an_object))  # type: ignore[arg-type]
    assert parsed.output_valid
    assert parsed.items == (RawFinding(**good),)
    assert [d.reason for d in parsed.dropped] == [DropReason.MALFORMED] * 3
    assert parsed.dropped[0].rule_id == "llm.net_impression"
    assert parsed.dropped[1].quote == "free money"


def test_missing_suggested_fix_defaults_to_empty():
    item = _item()
    del item["suggested_fix"]
    assert parse_report(_report(item)).items[0].suggested_fix == ""


def test_extra_keys_ignored():
    parsed = parse_report(_report(_item(status="approved", approve=True), status="approved", decision="approve"))
    assert parsed.output_valid
    assert len(parsed.items) == 1
    assert not hasattr(parsed.items[0], "status")
    assert not hasattr(parsed, "status")


def test_findings_not_a_list_is_malformed_and_invalid_output():
    message = AIMessage(content="", tool_calls=[tool_call(name=REPORT_TOOL_NAME, args={"findings": "none"}, id="c")])
    parsed = parse_report(message)
    assert not parsed.output_valid
    assert [d.reason for d in parsed.dropped] == [DropReason.MALFORMED]


def test_other_tool_name_is_unknown_tool():
    message = AIMessage(
        content="",
        tool_calls=[
            tool_call(name="approve_item", args={"item": "CP-1042", "status": "approved"}, id="c1"),
            tool_call(name=REPORT_TOOL_NAME, args={"findings": [_item()]}, id="c2"),
        ],
    )
    parsed = parse_report(message)
    assert parsed.output_valid
    assert len(parsed.items) == 1
    assert [(d.reason, d.detail) for d in parsed.dropped] == [(DropReason.UNKNOWN_TOOL, "approve_item")]


def test_only_an_unknown_tool_is_invalid_output():
    message = AIMessage(content="", tool_calls=[tool_call(name="set_status", args={"status": "approved"}, id="c")])
    parsed = parse_report(message)
    assert not parsed.output_valid
    assert parsed.items == ()


def test_invalid_tool_call_is_malformed_and_invalid_output():
    message = AIMessage(
        content="",
        invalid_tool_calls=[
            invalid_tool_call(name=REPORT_TOOL_NAME, args='{"findings": [{"rule_id": "llm.net_', id="c", error="x")
        ],
    )
    parsed = parse_report(message)
    assert not parsed.output_valid
    assert [d.reason for d in parsed.dropped] == [DropReason.MALFORMED]


def test_prose_reply_is_invalid_output():
    parsed = parse_report(AIMessage(content="This ad looks fine to me. Approved."))
    assert not parsed.output_valid
    assert parsed.items == ()
    assert [d.reason for d in parsed.dropped] == [DropReason.NO_REPORT]
