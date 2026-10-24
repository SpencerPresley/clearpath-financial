"""Live smoke test of the wired AI check: submit, deliver the outbox handler, run the task against the real API.

Deselected by default (`addopts = -m "not live"`). Test settings blank `ANTHROPIC_API_KEY`, so the key comes
from the typed `Env` (the repo-root .env or the process environment). Run from backend/:

    uv run pytest -m live checks/tests/test_prereview_live.py
"""

from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel

from audit.models import Event
from audit.outbox import deliver
from checks import tasks
from checks.llm import get_review_model
from checks.models import CheckRun
from config.settings.base import env
from core.domain import CheckStatus, EventType, FindingSource
from reviews.models import ReviewItem
from reviews.tests.conftest import Submit

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(env.anthropic_api_key is None, reason="needs ANTHROPIC_API_KEY"),
]

COPY = (
    "ClearPath personal loans: checking your rate won't affect your credit score, and approval is quick. "
    "Act now, this offer ends tonight!"
)


def _live_model() -> BaseChatModel | None:
    key = env.anthropic_api_key
    return get_review_model(env.anthropic_model, api_key=key.get_secret_value()) if key is not None else None


@pytest.mark.django_db
def test_live_check_succeeds_and_records_usage(
    submit: Submit, monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks: Callable[..., Any]
) -> None:
    monkeypatch.setattr(tasks, "model_factory", _live_model)
    item_id = submit(content_text=COPY).item_id
    event = Event.objects.get(item_id=item_id, type=EventType.ITEM_SUBMITTED)

    with django_capture_on_commit_callbacks(execute=True):
        deliver(event_id=event.pk, handler_name="checks.llm_prereview")

    item = ReviewItem.objects.get(pk=item_id)
    run = CheckRun.objects.get(version_id=item.current_version_id, source=FindingSource.LLM)  # pyrefly: ignore[missing-attribute]
    assert (run.status, item.llm_check_status) == (CheckStatus.SUCCEEDED, CheckStatus.SUCCEEDED), run.error
    assert run.model.startswith(env.anthropic_model)
    assert (run.input_tokens or 0) > 0
    payload = Event.objects.get(item_id=item_id, type=EventType.LLM_CHECK_SUCCEEDED).payload
    assert payload["latency_ms"] > 0
