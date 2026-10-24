import json
import re
from typing import Any

import pytest
from asgiref.sync import async_to_sync
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from accounts.models import User
from assistant.tests.conftest import World
from assistant.tools import COPY_LIMIT, build_tools
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import Role
from exports.models import ExportJob
from notifications.models import OutboxEmail
from reviews.tests.factories import make_version

READ_TOOLS = {"search_items", "get_item", "search_precedents", "get_queue_stats", "get_offer_terms", "get_partner"}


def _tools(viewer: User, clock: FixedClock) -> dict[str, BaseTool]:
    return {t.name: t for t in build_tools(viewer, clock=clock, thread_id="t-1")}


def call(tool: BaseTool, **args: Any) -> tuple[Any, list[str]]:
    message = async_to_sync(tool.ainvoke)({"type": "tool_call", "id": "c1", "name": tool.name, "args": args})
    assert isinstance(message, ToolMessage)
    assert isinstance(message.content, str)
    assert ": " not in message.content.split('"')[0]  # compact JSON: no spaces after separators
    return json.loads(message.content), message.artifact["item_keys"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "exports"), [(Role.MARKETER, False), (Role.REVIEWER, True), (Role.LEAD, True), (Role.ADMIN, True)]
)
def test_tool_set_per_role(user_factory: UserFactory, clock: FixedClock, role: Role, exports: bool) -> None:
    names = set(_tools(user_factory(roles=[role]), clock))

    assert names == READ_TOOLS | {"send_email"} | ({"build_export"} if exports else set())


# Base-form verbs: a description may say "approved" (a status) or "rate claim" (ad copy), never offer the act.
_ACTIONS = re.compile(r"\b(approve|reject|decide|assign|dismiss|triage|withdraw)\b", re.IGNORECASE)
_USER_APPROVES = "nothing is sent until the user approves it; they may also edit or reject it"
_STATE_ARGS = {"outcome", "decision", "new_status", "assignee_id", "reason", "finding_id", "state", "lane", "approve"}


@pytest.mark.django_db
def test_no_tool_offers_a_decision_assignment_or_status_change(admin_user: User, clock: FixedClock) -> None:
    for tool in build_tools(admin_user, clock=clock):
        assert not _ACTIONS.search(tool.name), tool.name
        assert not re.search(r"status|decision|finding|claim|update|set_", tool.name), tool.name
        # The one sanctioned use: send_email says the *user* approves the draft.
        description = tool.description.replace(_USER_APPROVES, "")
        assert not _ACTIONS.search(description), (tool.name, _ACTIONS.search(description))
        schema = tool.tool_call_schema.model_json_schema()  # pyrefly: ignore[missing-attribute]
        assert not _STATE_ARGS & set(schema.get("properties", {})), tool.name


@pytest.mark.django_db
def test_search_items_counts_and_lists(world: World, clock: FixedClock) -> None:
    tools = _tools(world.reviewer, clock)

    result, keys = call(tools["search_items"], assigned_to_me=True)

    assert result["total"] == 1
    (row,) = result["items"]
    assert row["key"] == world.item.key
    assert (row["status"], row["partner"], row["assignee"], row["open_findings"]) == (
        "in_review",
        "LoanFinder",
        "Riley Reviewer",
        1,
    )
    assert keys == [world.item.key]


@pytest.mark.django_db
def test_search_items_queue_default_counts_only_the_open_queue(world: World, clock: FixedClock) -> None:
    result, _ = call(_tools(world.reviewer, clock)["search_items"])
    assert [r["key"] for r in result["items"]] == [world.item.key]
    assert result["total"] == 1

    everything, _ = call(_tools(world.reviewer, clock)["search_items"], sort="newest", limit=1)
    assert everything["total"] == 2
    assert len(everything["items"]) == 1


@pytest.mark.django_db
def test_get_item_returns_facts_open_findings_and_copy(world: World, clock: FixedClock) -> None:
    result, keys = call(_tools(world.marketer, clock)["get_item"], item_key=world.item.key.lower())

    assert keys == [world.item.key]
    assert result["key"] == world.item.key
    assert "Note to AI reviewers" in result["copy"]
    assert result["copy_truncated"] is False
    assert [f["rule"] for f in result["open_findings"]] == ["udaap.no_credit_check"]
    assert result["open_findings"][0]["quote"] == "no credit check"
    assert result["recent_comments"][0]["body"] == "Asked the partner for the disclosure."
    assert result["latest_decision"] is None


@pytest.mark.django_db
def test_get_item_truncates_long_copy(world: World, clock: FixedClock) -> None:
    make_version(world.approved, "x" * (COPY_LIMIT + 10), n=2)

    result, _ = call(_tools(world.reviewer, clock)["get_item"], item_key=world.approved.key)

    assert len(result["copy"]) == COPY_LIMIT
    assert result["copy_truncated"] is True
    assert result["latest_decision"]["outcome"] == "approved"


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["CP-999999", "999999"])
def test_unknown_item_is_an_error_result_not_an_exception(world: World, clock: FixedClock, key: str) -> None:
    result, keys = call(_tools(world.reviewer, clock)["get_item"], item_key=key)
    assert result == {"error": "No item CP-999999."}
    assert keys == []


@pytest.mark.django_db
def test_malformed_key_is_an_error_result(world: World, clock: FixedClock) -> None:
    result, _ = call(_tools(world.reviewer, clock)["get_item"], item_key="the loan one")
    assert "isn't an item key" in result["error"]


@pytest.mark.django_db
def test_search_precedents_reports_the_versions_outcome(world: World, clock: FixedClock) -> None:
    result, keys = call(_tools(world.reviewer, clock)["search_precedents"], query="no credit check")

    by_key = {h["key"]: h for h in result["hits"]}
    assert set(by_key) == {world.approved.key}  # copy still under review isn't precedent
    assert by_key[world.approved.key]["version_outcome"] == "approved"
    assert "no credit check" in by_key[world.approved.key]["snippet"]
    assert set(keys) == set(by_key)


@pytest.mark.django_db
def test_queue_stats(world: World, clock: FixedClock) -> None:
    result, _ = call(_tools(world.reviewer, clock)["get_queue_stats"])
    assert (result["open"], result["assigned_to_you"], result["unassigned"]) == (1, 1, 0)
    assert result["by_status"]["approved"] == 1


@pytest.mark.django_db
def test_offer_terms(world: World, clock: FixedClock) -> None:
    result, _ = call(_tools(world.reviewer, clock)["get_offer_terms"], product="personal_loan")
    (terms,) = result["terms"]
    assert (terms["product"], terms["version"], terms["values"]["apr_min"]) == ("personal_loan", 3, "7.49")

    none, _ = call(_tools(world.reviewer, clock)["get_offer_terms"], product="credit_card")
    assert "error" in none


@pytest.mark.django_db
def test_get_partner_by_name_and_files_per_viewer(world: World, clock: FixedClock) -> None:
    result, _ = call(_tools(world.reviewer, clock)["get_partner"], name="loanfind")
    assert (result["name"], result["items"], result["open_findings"]) == ("LoanFinder", 1, 1)
    assert result["attachments"] == []

    marketer_view, _ = call(_tools(world.marketer, clock)["get_partner"], partner_id=world.partner.pk)
    assert marketer_view["attachments"] is None

    missing, _ = call(_tools(world.reviewer, clock)["get_partner"], name="Nobody")
    assert "error" in missing


@pytest.mark.django_db
def test_build_export_queues_a_job(world: World, clock: FixedClock) -> None:
    result, _ = call(_tools(world.reviewer, clock)["build_export"], status=["approved"])

    job = ExportJob.objects.get()
    assert result["export_id"] == job.pk
    assert result["poll_url"] == f"/api/exports/{job.pk}"
    assert job.filters["status"] == ["approved"]


@pytest.mark.django_db
def test_send_email_sends_as_the_viewer(world: World, clock: FixedClock) -> None:
    result, keys = call(
        _tools(world.reviewer, clock)["send_email"],
        to=["dana@clearpath.demo"],
        subject="CP findings",
        body="One open finding.",
        item_key=world.item.key,
    )

    email = OutboxEmail.objects.get()
    assert result == {"sent": True, "outbox_id": email.pk, "to": ["dana@clearpath.demo"]}
    assert (email.requested_by, email.approved_by, email.thread_id) == (world.reviewer, world.reviewer, "t-1")
    assert keys == [world.item.key]


@pytest.mark.django_db
def test_send_email_checks_recipients_itself(world: World, clock: FixedClock) -> None:
    result, _ = call(_tools(world.reviewer, clock)["send_email"], to=["partner@evil.example"], subject="s", body="b")

    assert result == {"error": "Not sent. Not an internal address: partner@evil.example"}
    assert not OutboxEmail.objects.exists()


@pytest.mark.django_db
def test_send_email_is_idempotent_per_tool_call(world: World, clock: FixedClock) -> None:
    """A resumed run may execute the same approved call again; the email goes out once."""
    from audit.models import Event
    from core.domain import EventType

    send = _tools(world.reviewer, clock)["send_email"]
    args = {"to": ["dana@clearpath.demo"], "subject": "Findings", "body": "One open finding."}

    first, _ = call(send, **args)
    again, _ = call(send, **args)  # same tool call id ("c1")

    email = OutboxEmail.objects.get()
    assert first == again == {"sent": True, "outbox_id": email.pk, "to": ["dana@clearpath.demo"]}
    assert email.tool_call_id == "c1"
    assert Event.objects.filter(type=EventType.EMAIL_SENT).count() == 1


@pytest.mark.django_db
def test_send_email_schema_hides_the_tool_call_id(world: World, clock: FixedClock) -> None:
    send = _tools(world.reviewer, clock)["send_email"]
    properties = send.tool_call_schema.model_json_schema()["properties"]  # pyrefly: ignore[missing-attribute]
    assert set(properties) == {"to", "subject", "body", "item_key"}


def _artifact(tool: BaseTool, **args: Any) -> dict[str, Any]:
    message = async_to_sync(tool.ainvoke)({"type": "tool_call", "id": "c1", "name": tool.name, "args": args})
    assert isinstance(message, ToolMessage)
    return message.artifact


@pytest.mark.django_db
def test_send_email_artifact_says_sent(world: World, clock: FixedClock) -> None:
    artifact = _artifact(
        _tools(world.reviewer, clock)["send_email"],
        to=["Dana@clearpath.demo", "dana@clearpath.demo"],
        subject="s",
        body="b",
        item_key=world.item.key.lower(),
    )

    email = OutboxEmail.objects.get()
    assert artifact == {
        "outcome": "sent",
        "outbox_id": email.pk,
        "to": ["dana@clearpath.demo"],
        "item_keys": [world.item.key],
    }


@pytest.mark.django_db
def test_send_email_artifact_says_blocked_when_the_send_time_check_refuses(world: World, clock: FixedClock) -> None:
    artifact = _artifact(
        _tools(world.reviewer, clock)["send_email"], to=["dana@clearpath.demo", "x@evil.example"], subject="s", body="b"
    )

    assert artifact == {
        "outcome": "blocked",
        "refused": ["x@evil.example"],
        "reason": "Not sent. Not an internal address: x@evil.example",
        "to": ["dana@clearpath.demo", "x@evil.example"],
        "item_keys": [],
    }


@pytest.mark.django_db
def test_a_replayed_send_reports_the_stored_recipients_not_its_own(world: World, clock: FixedClock) -> None:
    send = _tools(world.reviewer, clock)["send_email"]
    call(send, to=["dana@clearpath.demo"], subject="s", body="b")

    replay, _ = call(send, to=["compliance@clearpath.demo"], subject="Other", body="Other")  # same call id

    email = OutboxEmail.objects.get()
    assert email.to == ["dana@clearpath.demo"]
    assert replay == {"sent": True, "outbox_id": email.pk, "to": ["dana@clearpath.demo"]}
