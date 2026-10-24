"""Thread lifecycle and the run lock. A thread is per-user UI state (like a saved view), so these write no
Event; the emails a thread sends do (`EMAIL_SENT`, in `assistant.email`)."""

import re
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from django.db.models import Q

from accounts.models import User
from assistant.models import AssistantThread
from assistant.selectors import owned_thread
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Role
from core.errors import Conflict
from core.permissions import require_role

# A run normally ends well inside this (12 model calls, each capped at ~4 min with retries is the far tail);
# a lock older than this belongs to a process that died, and the next run takes it over.
STALE_RUN: Final = timedelta(minutes=10)
TITLE_LENGTH: Final = 80


def create_thread(*, owner: User, clock: Clock = SYSTEM_CLOCK) -> AssistantThread:
    require_role(owner, *Role)  # any staff role; a user with none (deactivated) gets 403
    now = clock.now()
    return AssistantThread.objects.create(owner=owner, created_at=now, updated_at=now)


def claim_run(*, thread_id: UUID, owner: User, clock: Clock = SYSTEM_CLOCK) -> datetime:
    """Take the thread's run lock in one conditional UPDATE, so two tabs can't both run an agent on one
    checkpoint. Returns the claim time, which `release_run` must present."""
    require_role(owner, *Role)
    now = clock.now()
    free = Q(running_since__isnull=True) | Q(running_since__lt=now - STALE_RUN)
    if not AssistantThread.objects.filter(free, pk=thread_id, owner=owner).update(running_since=now):
        owned_thread(owner=owner, thread_id=thread_id)  # someone else's or missing: 404, not 409
        raise Conflict("A reply is already running in this thread.")
    return now


def thread_title(message: str) -> str:
    collapsed = re.sub(r"\s+", " ", message).strip()
    return collapsed if len(collapsed) <= TITLE_LENGTH else f"{collapsed[: TITLE_LENGTH - 1].rstrip()}…"


def release_run(
    *,
    thread_id: UUID,
    claimed_at: datetime,
    awaiting_approval: bool | None = None,
    first_message: str | None = None,
    clock: Clock = SYSTEM_CLOCK,
) -> None:
    """Drop the lock this run holds (a lock taken over after going stale isn't ours to drop) and record what
    the list view shows. `awaiting_approval=None` leaves the flag as it was (the run ended before we knew)."""
    mine = AssistantThread.objects.filter(pk=thread_id, running_since=claimed_at)
    changes: dict[str, object] = {"running_since": None, "updated_at": clock.now()}
    if awaiting_approval is not None:
        changes["awaiting_approval"] = awaiting_approval
    mine.update(**changes)
    if first_message:
        AssistantThread.objects.filter(pk=thread_id, title="").update(title=thread_title(first_message))
