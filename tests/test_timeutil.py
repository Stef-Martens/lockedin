from datetime import UTC, date, datetime

from lockedin.timeutil import parse_local, week_start

FMT = ["%d %b %Y, %H:%M"]


def test_week_start_sunday_late_evening_brussels():
    # Sun 25 Oct 2026 23:30 local (UTC+1 after DST ends) belongs to the week of Mon 19 Oct
    assert week_start(datetime(2026, 10, 25, 22, 30, tzinfo=UTC)) == date(2026, 10, 19)


def test_week_start_monday_early_local():
    # 23:30 UTC Sunday is already Mon 00:30 in Brussels
    assert week_start(datetime(2026, 10, 25, 23, 30, tzinfo=UTC)) == date(2026, 10, 26)


def test_parse_local_ambiguous_uses_first_occurrence():
    assert parse_local("25 Oct 2026, 02:30", FMT) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_parse_local_nonexistent_shifts_forward():
    assert parse_local("29 Mar 2026, 02:30", FMT) == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)


def test_parse_local_tries_formats_in_order():
    assert parse_local("2026-10-20 18:00:00", ["%d %b %Y, %H:%M", "%Y-%m-%d %H:%M:%S"]) == datetime(2026, 10, 20, 16, 0, tzinfo=UTC)
