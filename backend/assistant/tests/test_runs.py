import time

import pytest
from asgiref.sync import async_to_sync
from langgraph.checkpoint.memory import InMemorySaver

from accounts.models import User
from assistant import runs, services
from assistant.models import AssistantThread
from assistant.tests.fakes import SlowModel
from core.clock import FixedClock


@pytest.mark.django_db
def test_closing_the_stream_aborts_the_run_and_releases_the_lock(owner: User, clock: FixedClock) -> None:
    thread = services.create_thread(owner=owner, clock=clock)
    claimed_at = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)
    saver = InMemorySaver()

    class _Saver:
        async def __aenter__(self) -> InMemorySaver:
            return saver

        async def __aexit__(self, *exc: object) -> None:
            return None

    async def disconnect_mid_run() -> list[bytes]:
        stream = runs.stream_run(
            thread_id=thread.pk,
            viewer=owner,
            command=runs.StartRun(message_id="u1", content="hi"),
            claimed_at=claimed_at,
            model_factory=lambda: SlowModel(messages=iter(["Never finishes."]), delay=2),
            checkpointer_factory=_Saver,
            clock=clock,
        )
        frames = [await anext(stream)]
        while not frames[-1].startswith(b"event: values"):  # the run is going; the model is "thinking"
            frames.append(await anext(stream))
        await stream.aclose()  # what Django does when the client goes away
        return frames

    started = time.monotonic()
    frames = async_to_sync(disconnect_mid_run)()

    assert time.monotonic() - started < 1.5  # didn't wait for the model
    assert frames[0].startswith(b"event: lifecycle\n")
    assert not any(b'"completed"' in f or b'"failed"' in f for f in frames)
    thread.refresh_from_db()
    assert thread.running_since is None
    assert thread.title == "hi"


@pytest.mark.django_db
def test_release_leaves_a_taken_over_lock_alone(owner: User, clock: FixedClock) -> None:
    thread = services.create_thread(owner=owner, clock=clock)
    stale = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)
    clock.advance(services.STALE_RUN * 2)
    current = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)

    services.release_run(thread_id=thread.pk, claimed_at=stale, clock=clock)

    assert AssistantThread.objects.get(pk=thread.pk).running_since == current


def test_title_is_collapsed_and_capped() -> None:
    assert services.thread_title("  What's\n\twaiting   on me? ") == "What's waiting on me?"
    title = services.thread_title("word " * 40)
    assert len(title) == services.TITLE_LENGTH
    assert title.endswith("…")
