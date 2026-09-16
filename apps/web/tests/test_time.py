from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from labserver_web.config import load_settings
from labserver_web.time import (
    format_local_window,
    local_day_bounds,
    parse_local_datetime,
    today_in_zone,
)


def test_parse_local_datetime_converts_to_utc() -> None:
    zone = ZoneInfo("Asia/Shanghai")

    parsed = parse_local_datetime("2026-09-20T14:00", zone)

    assert parsed == datetime(2026, 9, 20, 6, 0, tzinfo=UTC)


def test_parse_local_datetime_rejects_explicit_timezone() -> None:
    zone = ZoneInfo("Asia/Shanghai")

    with pytest.raises(ValueError, match="must not include a timezone"):
        parse_local_datetime("2026-09-20T14:00:00+02:00", zone)


def test_local_day_bounds_are_utc() -> None:
    zone = ZoneInfo("Asia/Shanghai")

    start, end = local_day_bounds(date(2026, 9, 20), zone)

    assert start == datetime(2026, 9, 19, 16, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 20, 16, 0, tzinfo=UTC)


def test_today_in_zone_uses_local_calendar_day() -> None:
    zone = ZoneInfo("Asia/Shanghai")

    current = today_in_zone(datetime(2026, 9, 19, 17, 0, tzinfo=UTC), zone)

    assert current == date(2026, 9, 20)


def test_format_local_window_uses_selected_day() -> None:
    zone = ZoneInfo("Asia/Shanghai")
    day = date(2026, 9, 20)

    inside = format_local_window(
        datetime(2026, 9, 20, 6, 0, tzinfo=UTC),
        datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        zone,
        day,
    )
    crossing = format_local_window(
        datetime(2026, 9, 20, 6, 0, tzinfo=UTC),
        datetime(2026, 9, 20, 16, 0, tzinfo=UTC),
        zone,
        day,
    )

    assert inside == "14:00–18:00"
    assert crossing == "14:00–09-21 00:00"


def test_default_timezone_is_utc_for_development() -> None:
    settings = load_settings({})

    assert settings.timezone_name == "UTC"
    assert str(settings.timezone) == "UTC"


def test_invalid_timezone_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid LABSERVER_TIMEZONE"):
        load_settings({"LABSERVER_TIMEZONE": "Invalid/Timezone"})
