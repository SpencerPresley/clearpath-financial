from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from accounts.models import User
from assistant.models import AssistantThread
from core.errors import NotFound


@dataclass(frozen=True)
class ThreadRow:
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    awaiting_approval: bool


def thread_row(thread: AssistantThread) -> ThreadRow:
    return ThreadRow(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        awaiting_approval=thread.awaiting_approval,
    )


def owned_thread(*, owner: User, thread_id: UUID) -> AssistantThread:
    """The caller's thread. Someone else's is reported as missing, so ids don't leak who has threads."""
    thread = AssistantThread.objects.filter(pk=thread_id, owner=owner).first()
    if thread is None:
        raise NotFound.entity("thread", str(thread_id))
    return thread


def get_thread(*, owner: User, thread_id: UUID) -> ThreadRow:
    return thread_row(owned_thread(owner=owner, thread_id=thread_id))


def list_threads(*, owner: User, limit: int = 50) -> tuple[ThreadRow, ...]:
    threads = AssistantThread.objects.filter(owner=owner).order_by("-updated_at", "-created_at")[:limit]
    return tuple(thread_row(t) for t in threads)
