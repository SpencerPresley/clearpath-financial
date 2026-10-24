"""Thread lifecycle. A thread is per-user UI state (like a saved view), so creating one writes no Event; the
emails a thread sends do (`EMAIL_SENT`, in `assistant.email`)."""

from accounts.models import User
from assistant.models import AssistantThread
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Role
from core.permissions import require_role


def create_thread(*, owner: User, clock: Clock = SYSTEM_CLOCK) -> AssistantThread:
    require_role(owner, *Role)  # any staff role; a user with none (deactivated) gets 403
    now = clock.now()
    return AssistantThread.objects.create(owner=owner, created_at=now, updated_at=now)
