"""The AI pre-review lifecycle (`checks.prereview`, `checks.tasks`): handler, task, status, retry, reconciliation.

The model is a scripted `GenericFakeChatModel` handed in through `checks.tasks.model_factory`; Celery runs
eagerly in tests, so `.delay()` and `self.retry()` execute synchronously (countdowns ignored).
"""

import dataclasses
import threading
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import anthropic
import httpx2
import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client
from langchain_core.language_models import BaseChatModel

from accounts.models import User
from audit.models import Event
from audit.outbox import REGISTRY, deliver, dispatch_pending
from checks import handlers, prereview, tasks
from checks.llm import LlmReviewResult
from checks.llm.tests.fakes import RaisingModel, fake, finding, report
from checks.models import CheckRun, Finding
from checks.prereview import STUCK_AFTER
from core.clock import FixedClock
from core.domain import (
    CheckStatus,
    DecisionOutcome,
    EventType,
    FindingSource,
    FindingState,
    ItemStatus,
    LlmFailureCode,
    Severity,
    VersionOrigin,
)
from core.errors import InvalidInput
from reviews.assignment import locked_item
from reviews.decisions import DecisionInput, record_decision
from reviews.models import ReviewItem, Version
from reviews.records import get_item_detail
from reviews.tests.conftest import Submit, dismiss_all
from reviews.versions import create_version, resubmit_item

HANDLER = "checks.llm_prereview"
COPY = "Personal loans from ClearPath. Apply online in minutes. Act now, this offer ends tonight!"
PRESSURE = "Act now, this offer ends tonight!"

type Models = list[BaseChatModel | None]
type OnCommit = Callable[..., Any]


def _good() -> BaseChatModel:
    return fake(report(finding(COPY, "llm.pressure_tactics", PRESSURE, suggested_fix="Apply online today.")))


def _status_error(code: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(code, request=request)
    return anthropic.APIStatusError(f"status {code}", response=response, body=None)  # pyrefly: ignore[bad-argument-type]


def _down() -> BaseChatModel:
    return RaisingModel(messages=iter([]), error=_status_error(529))


def _refused() -> BaseChatModel:
    return RaisingModel(messages=iter([]), error=_status_error(400))


def _prose() -> BaseChatModel:
    return fake("I looked at the ad and it seems fine.")


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch, clock: FixedClock) -> None:
    monkeypatch.setattr(handlers, "clock", clock)
    monkeypatch.setattr(tasks, "clock", clock)


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch, clock: FixedClock) -> Iterator[Models]:
    """Models handed to successive attempts, in order. Asserts every scripted model was used."""
    queue: Models = []
    monkeypatch.setattr(tasks, "model_factory", lambda: queue.pop(0))
    yield queue
    assert queue == [], "scripted models left unused"


@pytest.fixture
def submitted(submit: Submit) -> Callable[..., int]:
    def run(content_text: str = COPY) -> int:
        return submit(content_text=content_text).item_id

    return run


def _item(item_id: int) -> ReviewItem:
    return ReviewItem.objects.select_related("current_version").get(pk=item_id)


def _version_id(item_id: int) -> int:
    version = _item(item_id).current_version
    assert version is not None
    return version.pk


def _event(item_id: int, event_type: EventType) -> Event:
    return Event.objects.get(item_id=item_id, type=event_type)


def _events(item_id: int, event_type: EventType) -> list[Event]:
    return list(Event.objects.filter(item_id=item_id, type=event_type).order_by("id"))


def _llm_findings(version_id: int) -> list[Finding]:
    return list(Finding.objects.filter(version_id=version_id, source=FindingSource.LLM).order_by("pk"))


def _run_handler(item_id: int, capture: OnCommit, event_type: EventType = EventType.ITEM_SUBMITTED) -> None:
    """Deliver the item's latest `event_type` to the handler and run what it enqueues on commit."""
    event = Event.objects.filter(item_id=item_id, type=event_type).latest("id")
    with capture(execute=True):
        deliver(event_id=event.pk, handler_name=HANDLER)


# --- the handler -----------------------------------------------------------------------------------------------


def test_handler_is_registered_only_for_submission_events() -> None:
    spec = REGISTRY.get(HANDLER)
    assert spec.event_types == {
        EventType.ITEM_SUBMITTED,
        EventType.ITEM_RESUBMITTED,
        EventType.ITEM_NEW_ROUND_STARTED,
    }
    assert HANDLER not in {s.name for s in REGISTRY.for_type(EventType.VERSION_CREATED)}


@pytest.mark.django_db
def test_handler_requests_a_check_and_enqueues_on_commit(
    submitted: Callable[..., int], monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks: OnCommit
) -> None:
    enqueued: list[int] = []
    monkeypatch.setattr(prereview, "enqueue", enqueued.append)
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    version_id = _version_id(item_id)
    run = CheckRun.objects.get(version_id=version_id, source=FindingSource.LLM)
    version = Version.objects.get(pk=version_id)
    assert (run.status, run.attempts, run.content_sha256) == (CheckStatus.PENDING, 0, version.content_sha256)
    assert run.ruleset_key == prereview.ruleset_key("claude-haiku-5-5")
    requested = _event(item_id, EventType.LLM_CHECK_REQUESTED)
    assert requested.payload == {"version_id": version_id, "check_run_id": run.pk, "retry": False}
    assert requested.actor_id is None  # pyrefly: ignore[missing-attribute]
    assert enqueued == [version_id]
    assert _item(item_id).llm_check_status == CheckStatus.PENDING


@pytest.mark.django_db
def test_reviewer_edit_and_fast_track_versions_get_no_ai_delivery(
    submitted: Callable[..., int], reviewer: User, lead: User, clock: FixedClock
) -> None:
    item_id = submitted()
    with transaction.atomic():
        item = locked_item(item_id)
        base = item.current_version
        create_version(
            item=item, text=COPY + " ", author=reviewer, origin=VersionOrigin.REVIEWER_EDIT, based_on=base, clock=clock
        )
        create_version(
            item=item, text=COPY + "  ", author=lead, origin=VersionOrigin.FAST_TRACK, based_on=base, clock=clock
        )
    delivered: list[tuple[int, str]] = []
    # Drain everything recorded so far; only the submission should reach the AI handler.
    while dispatch_pending(enqueue=lambda e, h: delivered.append((e, h))).events:
        pass
    llm_events = [Event.objects.get(pk=e).type for e, h in delivered if h == HANDLER]
    assert llm_events == [EventType.ITEM_SUBMITTED]


# --- one attempt ------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_happy_path_persists_ai_findings_and_unblocks_approve(
    submitted: Callable[..., int],
    models: Models,
    reviewer: User,
    clock: FixedClock,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    models.append(_good())
    item_id = submitted()
    open_before = _item(item_id).open_findings_count

    _run_handler(item_id, django_capture_on_commit_callbacks)

    item = _item(item_id)
    version_id = _version_id(item_id)
    [ai] = _llm_findings(version_id)
    assert (ai.rule_id, ai.severity, ai.state) == ("llm.pressure_tactics", Severity.WARNING, FindingState.OPEN)
    assert (ai.span_start, ai.span_end, ai.quote) == (
        COPY.index(PRESSURE),
        COPY.index(PRESSURE) + len(PRESSURE),
        PRESSURE,
    )
    assert COPY[ai.span_start : ai.span_end] == ai.quote  # pyrefly: ignore[bad-index]
    assert ai.citation == "12 U.S.C. 5531, 5536(a)(1)(B)"
    assert ai.suggested_fix == "Apply online today."
    assert item.llm_check_status == CheckStatus.SUCCEEDED
    assert item.open_findings_count == open_before + 1

    run = CheckRun.objects.get(version_id=version_id, source=FindingSource.LLM)
    assert (run.status, run.findings_count, run.dropped_findings_count, run.attempts) == (
        CheckStatus.SUCCEEDED,
        1,
        0,
        1,
    )
    assert (run.model, run.input_tokens, run.output_tokens) == ("claude-haiku-5-5-20261001", 1800, 120)
    assert run.finished_at == clock.now()
    started = _event(item_id, EventType.LLM_CHECK_STARTED)
    assert started.payload == {"version_id": version_id, "check_run_id": run.pk, "attempt": 1}
    payload = _event(item_id, EventType.LLM_CHECK_SUCCEEDED).payload
    assert payload["model"] == "claude-haiku-5-5-20261001"
    assert (payload["input_tokens"], payload["output_tokens"], payload["cache_read_tokens"]) == (1800, 120, 1500)
    assert payload["latency_ms"] >= 0
    assert (payload["findings_count"], payload["dropped_findings_count"], payload["dropped_by_reason"]) == (1, 0, {})
    assert (payload["current"], payload["attempt"]) == (True, 1)

    dismiss_all(item_id, reviewer, clock)
    data = DecisionInput(outcome=DecisionOutcome.APPROVED, version_n=1, reason="Deadline is real")
    record_decision(actor=reviewer, item_id=item_id, data=data, clock=clock)
    assert _item(item_id).status == ItemStatus.APPROVED


@pytest.mark.django_db
def test_dropped_findings_are_counted_by_reason(
    submitted: Callable[..., int], models: Models, django_capture_on_commit_callbacks: OnCommit
) -> None:
    models.append(fake(report(finding(COPY, "llm.pressure_tactics", "not in the copy at all"))))
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _llm_findings(_version_id(item_id)) == []
    assert _item(item_id).llm_check_status == CheckStatus.SUCCEEDED
    payload = _event(item_id, EventType.LLM_CHECK_SUCCEEDED).payload
    assert (payload["dropped_findings_count"], payload["dropped_by_reason"]) == (1, {"quote_not_found": 1})


@pytest.mark.django_db
def test_ai_findings_are_always_warnings(
    submitted: Callable[..., int],
    models: Models,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """Orchestrator ruling: the AI never blocks on its own judgment, whatever its rule says."""
    real = prereview.review_copy

    def blocking(*args: Any, **kwargs: Any) -> LlmReviewResult:
        result = real(*args, **kwargs)
        return dataclasses.replace(
            result, findings=tuple(dataclasses.replace(f, severity=Severity.BLOCKING) for f in result.findings)
        )

    monkeypatch.setattr(prereview, "review_copy", blocking)
    models.append(_good())
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert [f.severity for f in _llm_findings(_version_id(item_id))] == [Severity.WARNING]


@pytest.mark.django_db
def test_database_refuses_a_blocking_ai_finding(submitted: Callable[..., int], clock: FixedClock) -> None:
    version = Version.objects.get(pk=_version_id(submitted()))
    with pytest.raises(IntegrityError), transaction.atomic():
        Finding.objects.create(
            version=version,
            rule_id="llm.pressure_tactics",
            citation="x",
            source=FindingSource.LLM,
            severity=Severity.BLOCKING,
            message="m",
            created_at=clock.now(),
        )


@pytest.mark.django_db
def test_retryable_error_then_success(
    submitted: Callable[..., int], models: Models, django_capture_on_commit_callbacks: OnCommit
) -> None:
    models.extend([_down(), _good()])
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _item(item_id).llm_check_status == CheckStatus.SUCCEEDED
    assert [e.payload["attempt"] for e in _events(item_id, EventType.LLM_CHECK_STARTED)] == [1, 2]
    assert len(_llm_findings(_version_id(item_id))) == 1
    assert _events(item_id, EventType.LLM_CHECK_FAILED) == []
    run = CheckRun.objects.get(version_id=_version_id(item_id), source=FindingSource.LLM)
    assert (run.attempts, run.error) == (2, "")
    [scheduled] = _events(item_id, EventType.LLM_CHECK_RETRY_SCHEDULED)
    assert scheduled.payload == {
        "version_id": run.version_id,  # pyrefly: ignore[missing-attribute]
        "check_run_id": run.pk,
        "attempt": 1,
        "error": "The model provider returned 529.",
        "countdown_s": 30,
    }


@pytest.mark.django_db
def test_a_reenqueued_run_continues_its_retry_budget(
    submitted: Callable[..., int],
    models: Models,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """Three attempts already failed and the retry message was lost: the reconciler's re-enqueue gets one more
    call, not a fresh four."""
    monkeypatch.setattr(prereview, "enqueue", lambda _version_id: None)
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)
    CheckRun.objects.filter(version_id=_version_id(item_id)).update(attempts=prereview.MAX_ATTEMPTS - 1)
    models.append(_down())

    assert tasks.run_llm_prereview.delay(_version_id(item_id)).get() == "failed"

    failed = _event(item_id, EventType.LLM_CHECK_FAILED).payload
    assert (failed["code"], failed["attempt"]) == (LlmFailureCode.PROVIDER_UNAVAILABLE, prereview.MAX_ATTEMPTS)


@pytest.mark.django_db
def test_a_lost_retry_message_ends_failed(
    submitted: Callable[..., int],
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """After a requeue the run is pending and the item running. If every message is lost, the reconciler keeps
    re-enqueueing, then gives up at GIVE_UP_AFTER: the item ends failed, never running forever."""
    monkeypatch.setattr(prereview, "enqueue", lambda _version_id: None)
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)
    claimed = prereview.claim(version_id=_version_id(item_id), clock=clock)
    assert claimed is not None
    prereview.requeue(
        claim=claimed, error="The model provider returned 529.", countdown=30, invalid_output=False, clock=clock
    )
    assert _item(item_id).llm_check_status == CheckStatus.RUNNING
    for _ in range(2):  # requeued at +10 and +20 min
        clock.advance(STUCK_AFTER + timedelta(seconds=1))
        assert prereview.reconcile(clock=clock).failed == ()

    clock.advance(STUCK_AFTER)
    result = prereview.reconcile(clock=clock)

    assert result.failed == (claimed.run_id,)
    assert _item(item_id).llm_check_status == CheckStatus.FAILED
    failed = _event(item_id, EventType.LLM_CHECK_FAILED).payload
    assert (failed["code"], failed["error"]) == (LlmFailureCode.STUCK, prereview.GAVE_UP_MESSAGE)


@pytest.mark.django_db
def test_pending_item_without_a_run_gets_one(
    submitted: Callable[..., int],
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """The handler never ran for this version (e.g. submitted before it was deployed)."""
    enqueued: list[int] = []
    monkeypatch.setattr(prereview, "enqueue", enqueued.append)
    item_id = submitted()
    young = prereview.reconcile(clock=clock)
    clock.advance(STUCK_AFTER + timedelta(minutes=1))

    with django_capture_on_commit_callbacks(execute=True):
        result = prereview.reconcile(clock=clock)
    again = prereview.reconcile(clock=clock)

    assert young.requested == ()
    assert result.requested == (item_id,)
    assert again.requested == ()
    assert enqueued == [_version_id(item_id)]
    run = CheckRun.objects.get(version_id=_version_id(item_id), source=FindingSource.LLM)
    assert run.status == CheckStatus.PENDING
    assert _event(item_id, EventType.LLM_CHECK_REQUESTED).payload["check_run_id"] == run.pk


@pytest.mark.django_db
def test_soft_time_limit_fails_with_timeout(
    submitted: Callable[..., int],
    models: Models,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    def slow(*args: Any, **kwargs: Any) -> LlmReviewResult:
        raise SoftTimeLimitExceeded

    monkeypatch.setattr(prereview, "review_copy", slow)
    models.append(_good())
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _item(item_id).llm_check_status == CheckStatus.FAILED
    assert _event(item_id, EventType.LLM_CHECK_FAILED).payload["code"] == LlmFailureCode.TIMEOUT


@pytest.mark.django_db
def test_a_result_after_the_reconciler_failed_the_run_is_dropped(
    submitted: Callable[..., int],
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    monkeypatch.setattr(prereview, "enqueue", lambda _version_id: None)
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)
    claimed = prereview.claim(version_id=_version_id(item_id), clock=clock)
    assert claimed is not None
    clock.advance(STUCK_AFTER + timedelta(minutes=1))
    prereview.reconcile(clock=clock)

    prereview.attempt(claim=claimed, model_factory=_good, clock=clock)

    assert _llm_findings(_version_id(item_id)) == []
    assert _events(item_id, EventType.LLM_CHECK_SUCCEEDED) == []
    assert _item(item_id).llm_check_status == CheckStatus.FAILED
    assert CheckRun.objects.get(pk=claimed.run_id).status == CheckStatus.FAILED


@pytest.mark.django_db(transaction=True)
def test_no_transaction_is_open_during_the_model_call(
    submitted: Callable[..., int], models: Models, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real commits (no wrapping test transaction): the handler's on_commit fires and the task runs eagerly. An
    open transaction during the call would hold back the outbox dispatcher's snapshot horizon."""
    real = prereview.review_copy
    in_transaction: list[bool] = []

    def observed(*args: Any, **kwargs: Any) -> LlmReviewResult:
        in_transaction.append(connection.in_atomic_block)
        return real(*args, **kwargs)

    monkeypatch.setattr(prereview, "review_copy", observed)
    models.append(_good())
    item_id = submitted()
    event = Event.objects.filter(item_id=item_id, type=EventType.ITEM_SUBMITTED).latest("id")

    deliver(event_id=event.pk, handler_name=HANDLER)

    assert in_transaction == [False]
    assert _item(item_id).llm_check_status == CheckStatus.SUCCEEDED


@pytest.mark.django_db
def test_retries_run_out_then_failed_and_approve_needs_an_override(
    submitted: Callable[..., int],
    models: Models,
    reviewer: User,
    clock: FixedClock,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    models.extend([_down() for _ in range(prereview.MAX_ATTEMPTS)])
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _item(item_id).llm_check_status == CheckStatus.FAILED
    failed = _event(item_id, EventType.LLM_CHECK_FAILED).payload
    assert failed["code"] == LlmFailureCode.PROVIDER_UNAVAILABLE
    assert failed["attempt"] == prereview.MAX_ATTEMPTS
    assert "529" in failed["error"]
    run = CheckRun.objects.get(version_id=_version_id(item_id), source=FindingSource.LLM)
    assert (run.status, run.error, run.finished_at) == (CheckStatus.FAILED, failed["error"], clock.now())

    dismiss_all(item_id, reviewer, clock)
    data = DecisionInput(outcome=DecisionOutcome.APPROVED, version_n=1, reason="Checked by hand")
    with pytest.raises(InvalidInput):
        record_decision(actor=reviewer, item_id=item_id, data=data, clock=clock)
    override = dataclasses.replace(data, llm_override_reason="AI service down; read it line by line")
    record_decision(actor=reviewer, item_id=item_id, data=override, clock=clock)
    assert _item(item_id).status == ItemStatus.APPROVED


@pytest.mark.django_db
def test_non_retryable_error_fails_after_one_call(
    submitted: Callable[..., int], models: Models, django_capture_on_commit_callbacks: OnCommit
) -> None:
    models.append(_refused())
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _item(item_id).llm_check_status == CheckStatus.FAILED
    failed = _event(item_id, EventType.LLM_CHECK_FAILED).payload
    assert (failed["code"], failed["attempt"]) == (LlmFailureCode.PROVIDER_REFUSED, 1)
    assert "400" in failed["error"]


@pytest.mark.django_db
def test_unreadable_output_twice_is_failed_not_clean(
    submitted: Callable[..., int], models: Models, django_capture_on_commit_callbacks: OnCommit
) -> None:
    models.extend([_prose(), _prose()])
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _item(item_id).llm_check_status == CheckStatus.FAILED
    assert _event(item_id, EventType.LLM_CHECK_FAILED).payload["code"] == LlmFailureCode.INVALID_OUTPUT
    assert _events(item_id, EventType.LLM_CHECK_SUCCEEDED) == []


@pytest.mark.django_db
def test_unreadable_output_once_is_retried(
    submitted: Callable[..., int], models: Models, django_capture_on_commit_callbacks: OnCommit
) -> None:
    models.extend([_prose(), _good()])
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _item(item_id).llm_check_status == CheckStatus.SUCCEEDED
    assert _event(item_id, EventType.LLM_CHECK_SUCCEEDED).payload["attempt"] == 2


@pytest.mark.django_db
def test_no_api_key_fails_with_a_plain_reason(
    submitted: Callable[..., int],
    monkeypatch: pytest.MonkeyPatch,
    clock: FixedClock,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """Test settings carry no key, so the real factory returns None."""
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _item(item_id).llm_check_status == CheckStatus.FAILED
    failed = _event(item_id, EventType.LLM_CHECK_FAILED).payload
    assert failed["code"] == LlmFailureCode.NOT_CONFIGURED
    assert "API key" in failed["error"]


@pytest.mark.django_db
def test_item_detail_carries_the_failure_until_a_retry_succeeds(
    submitted: Callable[..., int],
    models: Models,
    reviewer: User,
    clock: FixedClock,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """The review screen shows why the check failed from the item itself, not from history."""
    models.extend([_refused(), _good()])
    item_id = submitted()
    client = Client()
    client.force_login(reviewer)
    assert client.get(f"/api/items/{item_id}").json()["llm_check_failure_code"] is None

    _run_handler(item_id, django_capture_on_commit_callbacks)
    failed = client.get(f"/api/items/{item_id}").json()
    with django_capture_on_commit_callbacks(execute=True):
        prereview.retry_check(actor=reviewer, item_id=item_id, clock=clock)
    retried = client.get(f"/api/items/{item_id}").json()

    assert failed["llm_check_status"] == "failed"
    assert failed["llm_check_failure_code"] == "provider_refused"
    assert failed["llm_check_failure_reason"].startswith("The AI service refused the request.")
    assert retried["llm_check_status"] == "succeeded"
    assert (retried["llm_check_failure_code"], retried["llm_check_failure_reason"]) == (None, None)


@pytest.mark.django_db
def test_item_detail_says_when_the_ai_check_isnt_configured(
    submitted: Callable[..., int], reviewer: User, django_capture_on_commit_callbacks: OnCommit
) -> None:
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)

    detail = get_item_detail(item_id=item_id)

    assert detail.llm_check_failure_code == LlmFailureCode.NOT_CONFIGURED
    assert detail.llm_check_failure_reason is not None
    assert "API key" in detail.llm_check_failure_reason


@pytest.mark.django_db
def test_item_detail_shows_the_current_versions_failure(
    submitted: Callable[..., int],
    models: Models,
    reviewer: User,
    marketer: User,
    clock: FixedClock,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """v1's check was refused; after a resubmit, v2's answer was unreadable twice. The item shows v2's reason."""
    models.extend([_refused(), _prose(), _prose()])
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)
    _changes_requested(item_id, reviewer, clock)
    resubmit_item(actor=marketer, item_id=item_id, content_text=COPY + " Terms apply.", clock=clock)
    assert get_item_detail(item_id=item_id).llm_check_failure_code is None  # v2 pending

    _run_handler(item_id, django_capture_on_commit_callbacks, EventType.ITEM_RESUBMITTED)

    detail = get_item_detail(item_id=item_id)
    assert detail.llm_check_status == CheckStatus.FAILED
    assert detail.llm_check_failure_code == LlmFailureCode.INVALID_OUTPUT


@pytest.mark.django_db
def test_settings_model_uses_the_configured_name_and_key(settings: Any) -> None:
    settings.ANTHROPIC_API_KEY = "sk-test"
    settings.ANTHROPIC_MODEL = "claude-haiku-5-5"
    model = prereview.settings_model()
    assert model is not None
    assert model.model == "claude-haiku-5-5"  # pyrefly: ignore[missing-attribute]
    assert model.anthropic_api_key.get_secret_value() == "sk-test"  # pyrefly: ignore[missing-attribute]
    settings.ANTHROPIC_API_KEY = None
    assert prereview.settings_model() is None


@pytest.mark.django_db
def test_unexpected_error_fails_the_run(
    submitted: Callable[..., int],
    models: Models,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    def boom(*args: Any, **kwargs: Any) -> LlmReviewResult:
        raise RuntimeError("bug")

    monkeypatch.setattr(prereview, "review_copy", boom)
    models.append(_good())
    item_id = submitted()

    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert _item(item_id).llm_check_status == CheckStatus.FAILED
    assert _event(item_id, EventType.LLM_CHECK_FAILED).payload["code"] == LlmFailureCode.ERROR


# --- stale versions, duplicates, carry-forward ----------------------------------------------------------------


def _changes_requested(item_id: int, reviewer: User, clock: FixedClock) -> None:
    data = DecisionInput(outcome=DecisionOutcome.CHANGES_REQUESTED, version_n=1, reason="Drop the deadline")
    record_decision(actor=reviewer, item_id=item_id, data=data, clock=clock)


@pytest.mark.django_db
def test_stale_version_keeps_findings_but_not_status(
    submitted: Callable[..., int],
    models: Models,
    marketer: User,
    reviewer: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """The marketer resubmits v2 while v1's call is in flight: v1 gets its findings, v2 stays pending."""
    item_id = submitted()
    v1 = _version_id(item_id)
    monkeypatch.setattr(prereview, "enqueue", lambda _version_id: None)
    _run_handler(item_id, django_capture_on_commit_callbacks)  # v1 pending, not yet run

    def resubmit_then_answer() -> BaseChatModel:
        _changes_requested(item_id, reviewer, clock)
        resubmit_item(actor=marketer, item_id=item_id, content_text="Personal loans from ClearPath.", clock=clock)
        return _good()

    monkeypatch.setattr(tasks, "model_factory", resubmit_then_answer)
    tasks.run_llm_prereview.delay(v1)

    item = _item(item_id)
    assert item.current_version is not None
    assert item.current_version.n == 2
    assert item.llm_check_status == CheckStatus.PENDING
    assert len(_llm_findings(v1)) == 1
    payload = _event(item_id, EventType.LLM_CHECK_SUCCEEDED).payload
    assert (payload["version_id"], payload["current"]) == (v1, False)
    assert CheckRun.objects.get(version_id=v1, source=FindingSource.LLM).status == CheckStatus.SUCCEEDED


@pytest.mark.django_db
def test_second_delivery_is_a_noop(
    submitted: Callable[..., int], models: Models, django_capture_on_commit_callbacks: OnCommit
) -> None:
    models.append(_good())  # one model: a second call would pop from an empty list
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)

    assert tasks.run_llm_prereview.delay(_version_id(item_id)).get() == "noop"

    assert len(_llm_findings(_version_id(item_id))) == 1
    assert len(_events(item_id, EventType.LLM_CHECK_SUCCEEDED)) == 1
    assert CheckRun.objects.filter(version_id=_version_id(item_id), source=FindingSource.LLM).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_claims_take_the_run_once(
    submitted: Callable[..., int], clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A duplicate delivery while the original is starting (acks_late redelivery, reconciler re-enqueue): two
    workers on separate connections race to claim; exactly one wins."""
    monkeypatch.setattr(prereview, "enqueue", lambda _version_id: None)
    item_id = submitted()
    event = Event.objects.filter(item_id=item_id, type=EventType.ITEM_SUBMITTED).latest("id")
    deliver(event_id=event.pk, handler_name=HANDLER)
    version_id = _version_id(item_id)
    barrier = threading.Barrier(2)
    claims: list[prereview.Claim | None] = []

    def worker() -> None:
        try:
            barrier.wait()
            claims.append(prereview.claim(version_id=version_id, clock=clock))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(c is not None for c in claims) == [False, True]
    assert len(_events(item_id, EventType.LLM_CHECK_STARTED)) == 1


@pytest.mark.django_db
def test_a_version_replaced_before_delivery_gets_no_check(
    submitted: Callable[..., int],
    marketer: User,
    reviewer: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    enqueued: list[int] = []
    monkeypatch.setattr(prereview, "enqueue", enqueued.append)
    item_id = submitted()
    v1 = _version_id(item_id)
    _changes_requested(item_id, reviewer, clock)
    resubmit_item(actor=marketer, item_id=item_id, content_text="Personal loans from ClearPath.", clock=clock)

    _run_handler(item_id, django_capture_on_commit_callbacks)  # v1's ITEM_SUBMITTED, delivered late

    assert not CheckRun.objects.filter(version_id=v1, source=FindingSource.LLM).exists()
    assert enqueued == []


@pytest.mark.django_db
def test_dismissal_carries_to_the_next_version(
    submitted: Callable[..., int],
    models: Models,
    marketer: User,
    reviewer: User,
    clock: FixedClock,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    models.extend([_good(), _good()])
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)
    dismiss_all(item_id, reviewer, clock, reason="The offer really ends tonight")
    _changes_requested(item_id, reviewer, clock)
    resubmit_item(actor=marketer, item_id=item_id, content_text=COPY, clock=clock)

    _run_handler(item_id, django_capture_on_commit_callbacks, EventType.ITEM_RESUBMITTED)

    [carried] = _llm_findings(_version_id(item_id))
    assert (carried.state, carried.reason) == (FindingState.DISMISSED, "The offer really ends tonight")
    assert carried.carried_from_id == _llm_findings(Version.objects.get(item_id=item_id, n=1).pk)[0].pk  # pyrefly: ignore[missing-attribute]
    assert _item(item_id).llm_check_status == CheckStatus.SUCCEEDED


# --- reconciliation ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_stuck_running_flips_to_failed(
    submitted: Callable[..., int],
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    monkeypatch.setattr(prereview, "enqueue", lambda _version_id: None)
    stuck_id, fresh_id = submitted(), submitted()
    for item_id in (stuck_id, fresh_id):
        _run_handler(item_id, django_capture_on_commit_callbacks)
    assert prereview.claim(version_id=_version_id(stuck_id), clock=clock) is not None
    clock.advance(STUCK_AFTER - timedelta(minutes=5))
    assert prereview.claim(version_id=_version_id(fresh_id), clock=clock) is not None
    clock.advance(timedelta(minutes=6))

    result = prereview.reconcile(clock=clock)

    assert result.failed == (CheckRun.objects.get(version_id=_version_id(stuck_id), source=FindingSource.LLM).pk,)
    assert _item(stuck_id).llm_check_status == CheckStatus.FAILED
    assert _event(stuck_id, EventType.LLM_CHECK_FAILED).payload["code"] == LlmFailureCode.STUCK
    assert _item(fresh_id).llm_check_status == CheckStatus.RUNNING


@pytest.mark.django_db
def test_stuck_run_on_a_replaced_version_leaves_the_item_alone(
    submitted: Callable[..., int],
    marketer: User,
    reviewer: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    monkeypatch.setattr(prereview, "enqueue", lambda _version_id: None)
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)
    v1 = _version_id(item_id)
    prereview.claim(version_id=v1, clock=clock)
    _changes_requested(item_id, reviewer, clock)
    resubmit_item(actor=marketer, item_id=item_id, content_text="Personal loans from ClearPath.", clock=clock)
    clock.advance(STUCK_AFTER + timedelta(minutes=1))

    prereview.reconcile(clock=clock)

    assert CheckRun.objects.get(version_id=v1, source=FindingSource.LLM).status == CheckStatus.FAILED
    assert _event(item_id, EventType.LLM_CHECK_FAILED).payload["current"] is False
    assert _item(item_id).llm_check_status == CheckStatus.PENDING


@pytest.mark.django_db
def test_stale_pending_is_requeued(
    submitted: Callable[..., int],
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """The enqueue was lost (Redis flushed): the pending run is sent again, once per STUCK_AFTER."""
    enqueued: list[int] = []
    monkeypatch.setattr(prereview, "enqueue", lambda version_id: None)
    old_id = submitted()
    _run_handler(old_id, django_capture_on_commit_callbacks)
    clock.advance(STUCK_AFTER + timedelta(minutes=1))
    new_id = submitted()
    _run_handler(new_id, django_capture_on_commit_callbacks)
    monkeypatch.setattr(prereview, "enqueue", enqueued.append)

    first = prereview.reconcile(clock=clock)
    again = prereview.reconcile(clock=clock)

    assert enqueued == [_version_id(old_id)]
    assert len(first.requeued) == 1
    assert again.requeued == ()
    assert _item(old_id).llm_check_status == CheckStatus.PENDING


# --- retry ------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_retry_from_failed_runs_a_new_check(
    submitted: Callable[..., int],
    models: Models,
    reviewer: User,
    clock: FixedClock,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    models.extend([_refused(), _good()])
    item_id = submitted()
    _run_handler(item_id, django_capture_on_commit_callbacks)
    assert _item(item_id).llm_check_status == CheckStatus.FAILED

    with django_capture_on_commit_callbacks(execute=True):
        prereview.retry_check(actor=reviewer, item_id=item_id, clock=clock)

    assert _item(item_id).llm_check_status == CheckStatus.SUCCEEDED
    runs = list(CheckRun.objects.filter(version_id=_version_id(item_id), source=FindingSource.LLM).order_by("pk"))
    assert [r.status for r in runs] == [CheckStatus.FAILED, CheckStatus.SUCCEEDED]
    requested = _events(item_id, EventType.LLM_CHECK_REQUESTED)[-1]
    assert (requested.payload["retry"], requested.actor_id) == (True, reviewer.pk)  # pyrefly: ignore[missing-attribute]


# --- the retry endpoint -----------------------------------------------------------------------------------------


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _failed(item_id: int) -> None:
    ReviewItem.objects.filter(pk=item_id).update(llm_check_status=CheckStatus.FAILED)


@pytest.mark.django_db
def test_retry_endpoint_requeues_a_failed_check(
    submitted: Callable[..., int],
    reviewer: User,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    enqueued: list[int] = []
    monkeypatch.setattr(prereview, "enqueue", enqueued.append)
    item_id = submitted()
    _failed(item_id)

    with django_capture_on_commit_callbacks(execute=True):
        response = _client(reviewer).post(f"/api/items/{item_id}/llm-check/retry")

    assert response.status_code == 202
    assert response.json()["llm_check_status"] == "pending"
    assert enqueued == [_version_id(item_id)]


@pytest.mark.django_db
def test_retry_endpoint_refuses_unless_failed(submitted: Callable[..., int], reviewer: User) -> None:
    item_id = submitted()

    response = _client(reviewer).post(f"/api/items/{item_id}/llm-check/retry")

    assert response.status_code == 409
    assert response.json()["code"] == "llm_check_not_failed"
    assert CheckRun.objects.filter(source=FindingSource.LLM).count() == 0


@pytest.mark.django_db
def test_retry_endpoint_is_for_reviewers(submitted: Callable[..., int], marketer: User) -> None:
    item_id = submitted()
    _failed(item_id)

    response = _client(marketer).post(f"/api/items/{item_id}/llm-check/retry")

    assert response.status_code == 403


@pytest.mark.django_db
def test_retry_refuses_once_the_item_is_decided(
    submitted: Callable[..., int], reviewer: User, clock: FixedClock
) -> None:
    item_id = submitted()
    _failed(item_id)
    _changes_requested(item_id, reviewer, clock)

    response = _client(reviewer).post(f"/api/items/{item_id}/llm-check/retry")

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_transition"
