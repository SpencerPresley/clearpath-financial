"""Injectable time (spec §6.2).

Services and time-relative selectors take `clock: Clock = SYSTEM_CLOCK`; tests pass a `FixedClock`.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final, Protocol

from django.utils import timezone


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant, timezone-aware (UTC)."""
        ...

    def today(self) -> date:
        """The current date in settings.TIME_ZONE."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(tz=UTC)

    def today(self) -> date:
        return timezone.localdate(self.now())


@dataclass
class FixedClock:
    at: datetime

    def __post_init__(self) -> None:
        if timezone.is_naive(self.at):
            raise ValueError("FixedClock needs an aware datetime")

    def now(self) -> datetime:
        return self.at

    def today(self) -> date:
        return timezone.localdate(self.at)

    def advance(self, delta: timedelta) -> None:
        self.at += delta


SYSTEM_CLOCK: Final[Clock] = SystemClock()
