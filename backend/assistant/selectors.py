import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from accounts.models import User
from assistant.models import AssistantThread
from core.errors import NotFound
from reviews.models import ReviewItem

# The run lock is a lease: a running stream renews it every RENEW_RUN, and one not renewed for STALE_RUN
# belongs to a request that died or never started its response; the next run takes it over.
STALE_RUN: Final = timedelta(seconds=60)
RENEW_RUN: Final = timedelta(seconds=15)
_ITEM_KEY: Final = re.compile(r"^\s*(?:CP-?)?(\d{1,12})\s*$", re.IGNORECASE)


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


def has_live_run(thread: AssistantThread, *, now: datetime) -> bool:
    """A request is running the agent on this thread right now (runs live only as long as their request)."""
    return thread.running_since is not None and thread.running_since >= now - STALE_RUN


def get_thread(*, owner: User, thread_id: UUID) -> ThreadRow:
    return thread_row(owned_thread(owner=owner, thread_id=thread_id))


def list_threads(*, owner: User, limit: int = 50) -> tuple[ThreadRow, ...]:
    threads = AssistantThread.objects.filter(owner=owner).order_by("-updated_at", "-created_at")[:limit]
    return tuple(thread_row(t) for t in threads)


def parse_item_key(key: str) -> int | None:
    """`CP-1042`, `cp-1042` or `1042` -> 1042; anything else -> None."""
    match = _ITEM_KEY.match(key)
    return int(match.group(1)) if match else None


def resolve_item_key(key: str) -> int | None:
    """The id of an existing item for this key, or None."""
    item_id = parse_item_key(key)
    if item_id is None or not ReviewItem.objects.filter(pk=item_id).exists():
        return None
    return item_id
