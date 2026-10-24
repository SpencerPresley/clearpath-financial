"""Calendar-month arithmetic for expiry and retention dates (no dateutil dependency for one helper)."""

import calendar
from datetime import date


def add_months[D: date](day: D, months: int) -> D:
    """Same day-of-month N months later, clamped to the month's last day (Jan 31 + 1 month = Feb 28/29).
    Works for dates and datetimes; a datetime keeps its time and zone."""
    years, month_index = divmod(day.month - 1 + months, 12)
    year, month = day.year + years, month_index + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))
