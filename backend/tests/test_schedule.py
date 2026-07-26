from datetime import datetime

from worker.schedule_utils import cron_matches_now, is_within_sync_window, parse_sync_days


def test_weekday_filter():
    monday = datetime(2026, 5, 18, 12, 0)  # Monday
    assert is_within_sync_window(active_days=[0], time_from="09:00", time_to="18:00", now=monday)
    assert not is_within_sync_window(active_days=[1], time_from="09:00", time_to="18:00", now=monday)


def test_time_window_inclusive():
    noon = datetime(2026, 5, 18, 12, 0)
    assert is_within_sync_window(active_days=[0], time_from="12:00", time_to="12:00", now=noon)
    assert not is_within_sync_window(active_days=[0], time_from="13:00", time_to="17:00", now=noon)


def test_overnight_window():
    late = datetime(2026, 5, 18, 23, 0)
    early = datetime(2026, 5, 19, 1, 0)  # Tuesday
    assert is_within_sync_window(active_days=[0], time_from="22:00", time_to="02:00", now=late)
    assert is_within_sync_window(active_days=[1], time_from="22:00", time_to="02:00", now=early)


def test_parse_days():
    assert parse_sync_days("[0,1,2]") == [0, 1, 2]
    assert parse_sync_days("broken") == [0, 1, 2, 3, 4]


def test_cron_matches_now_within_minute():
    now = datetime(2026, 5, 18, 12, 0, 30)
    assert cron_matches_now("0 12 * * *", now=now) is True
    assert cron_matches_now("0 13 * * *", now=now) is False
