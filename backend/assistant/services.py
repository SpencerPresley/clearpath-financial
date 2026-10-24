"""Thread lifecycle and the run lock. A thread is per-user UI state (like a saved view), so these write no
Event; the emails a thread sends do (`EMAIL_SENT`, in `assistant.email`)."""

import re
import uuid
from typing import Final
from uuid import UUID

from django.db.models import Q

from accounts.models import User
from assistant.models import AssistantThread
from assistant.selectors import STALE_RUN, owned_thread
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Role
from core.errors import Conflict
from core.permissions import require_role

TITLE_LENGTH: Final = 80


def create_thread(*, owner: User, clock: Clock = SYSTEM_CLOCK) -> AssistantThread:
    require_role(owner, *Role)  # any staff role; a user with none (deactivated) gets 403
    now = clock.now()
    return AssistantThread.objects.create(owner=owner, created_at=now, updated_at=now)


def claim_run(*, thread_id: UUID, owner: User, clock: Clock = SYSTEM_CLOCK) -> UUID:
    """Take the thread's run lease in one conditional UPDATE, so two tabs can't both run an agent on one
    checkpoint. Returns the claim's token: renewing and releasing need it. A lease nobody renews lapses after
    STALE_RUN, so a claim whose response never started (the client left first) frees itself."""
    require_role(owner, *Role)
    now = clock.now()
    token = uuid.uuid4()
    free = Q(running_since__isnull=True) | Q(running_since__lt=now - STALE_RUN)
    if not AssistantThread.objects.filter(free, pk=thread_id, owner=owner).update(running_since=now, run_token=token):
        owned_thread(owner=owner, thread_id=thread_id)  # someone else's or missing: 404, not 409
        raise Conflict("A reply is already running in this thread.")
    return token


def renew_run(*, thread_id: UUID, token: UUID, clock: Clock = SYSTEM_CLOCK) -> bool:
    """Extend the lease this run holds. False if it isn't ours any more (it lapsed and was taken over)."""
    return bool(AssistantThread.objects.filter(pk=thread_id, run_token=token).update(running_since=clock.now()))


def thread_title(message: str) -> str:
    collapsed = re.sub(r"\s+", " ", message).strip()
    return collapsed if len(collapsed) <= TITLE_LENGTH else f"{collapsed[: TITLE_LENGTH - 1].rstrip()}…"


def release_run(
    *,
    thread_id: UUID,
    token: UUID,
    awaiting_approval: bool | None = None,
    first_message: str | None = None,
    clock: Clock = SYSTEM_CLOCK,
) -> None:
    """Drop the lease this run holds (one taken over after lapsing isn't ours to drop) and record what the
    list view shows. `awaiting_approval=None` leaves the flag as it was (the run ended before we knew)."""
    changes: dict[str, object] = {"running_since": None, "run_token": None, "updated_at": clock.now()}
    if awaiting_approval is not None:
        changes["awaiting_approval"] = awaiting_approval
    AssistantThread.objects.filter(pk=thread_id, run_token=token).update(**changes)
    if first_message:
        AssistantThread.objects.filter(pk=thread_id, title="").update(title=thread_title(first_message))
