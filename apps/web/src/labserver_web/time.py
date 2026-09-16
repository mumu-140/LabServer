"""Local-timezone helpers for the shared schedule.

Core and the database always store UTC. The Web surface interprets naive
form input in the configured IANA timezone and renders stored UTC back in
that same zone, so the schedule speaks the lab's wall-clock language.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def parse_local_datetime(raw: str, zone: ZoneInfo) -> datetime:
    """Interpret a naive datetime-local value in `zone`; return UTC."""
    value = datetime.fromisoformat(raw)
    if value.tzinfo is not None:
        raise ValueError("datetime-local value must not include a timezone")
    return value.replace(tzinfo=zone).astimezone(UTC)


def local_day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC bounds of one local calendar day (local midnight to local midnight)."""
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def today_in_zone(now: datetime, zone: ZoneInfo) -> date:
    """The local calendar day for a given UTC instant."""
    return now.astimezone(zone).date()


def format_local_window(
    start_at: datetime,
    end_at: datetime,
    zone: ZoneInfo,
    selected_day: date,
) -> str:
    """Render a plan window in local time; annotate parts outside the day."""
    start_local = start_at.astimezone(zone)
    end_local = end_at.astimezone(zone)

    def fmt(value: datetime) -> str:
        if value.date() == selected_day:
            return value.strftime("%H:%M")
        return value.strftime("%m-%d %H:%M")

    return f"{fmt(start_local)}–{fmt(end_local)}"
