from datetime import datetime

from worker.schedule_utils import is_within_sync_window, parse_sync_days


def test_weekday_filter():
    monday = datetime(2026, 5, 18, 12, 0)  # Monday
    assert is_within_sync_window(active_days=[0], time_from="09:00", time_to="18:00", now=monday)
    assert not is_within_sync_window(active_days=[1], time_from="09:00", time_to="18:00", now=monday)


def test_parse_days():
    assert parse_sync_days("[0,1,2]") == [0, 1, 2]
