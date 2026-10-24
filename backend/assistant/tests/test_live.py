"""Live smoke test against the real model. Deselected by default (`addopts = -m "not live"`). Run with:

    ANTHROPIC_API_KEY=... uv run pytest -m live assistant

Checks the wiring (the request is accepted, tools reach the model, the stream ends cleanly), not quality.
"""

import json

import pytest
from django.conf import settings
from django.test import Client

from accounts.models import User

pytestmark = [
    pytest.mark.live,
    pytest.mark.django_db,
    pytest.mark.skipif(not settings.ASSISTANT_ANTHROPIC_API_KEY, reason="needs ANTHROPIC_API_KEY"),
]


def test_live_haiku_answers_a_queue_question_with_get_queue_stats(owner: User) -> None:
    client = Client()
    client.force_login(owner)
    thread_id = client.post("/api/assistant/threads").json()["id"]

    response = client.post(
        f"/api/assistant/threads/{thread_id}/runs",
        {"message": {"id": "u1", "content": "How many items are waiting on review?"}},
        content_type="application/json",
    )

    events = [
        json.loads(block.split("\ndata: ", 1)[1])
        for block in b"".join(response).decode().split("\n\n")
        if block.startswith("event: ")
    ]
    started = [
        e["params"]["data"]["tool_name"]
        for e in events
        if e["method"] == "tools" and e["params"]["data"]["event"] == "tool-started"
    ]
    assert "get_queue_stats" in started
    assert events[-1]["params"]["data"]["event"] == "completed", events[-1]
