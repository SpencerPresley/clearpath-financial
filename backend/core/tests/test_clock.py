from datetime import UTC, date, datetime, timedelta

import pytest

from core.clock import SYSTEM_CLOCK, FixedClock


def test_fixed_clock_returns_its_instant_and_advances() -> None:
    clock = FixedClock(datetime(2026, 10, 24, 23, 30, tzinfo=UTC))

    assert clock.now() == datetime(2026, 10, 24, 23, 30, tzinfo=UTC)
    clock.advance(timedelta(hours=1))
    assert clock.now() == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_fixed_clock_today_is_the_local_date(settings: pytest.FixtureRequest) -> None:
    clock = FixedClock(datetime(2026, 10, 25, 0, 30, tzinfo=UTC))

    assert clock.today() == date(2026, 10, 25)


def test_fixed_clock_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="aware"):
        FixedClock(datetime(2026, 10, 24))  # noqa: DTZ001


def test_system_clock_is_aware() -> None:
    assert SYSTEM_CLOCK.now().tzinfo is not None
