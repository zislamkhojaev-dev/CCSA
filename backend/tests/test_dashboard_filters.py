"""Tests for dashboard filter parsing."""

from datetime import datetime, timezone

from app.services.dashboard_filters import parse_dashboard_filters

UTC = timezone.utc


def test_parse_preset_period():
    f = parse_dashboard_filters(period_days=30)
    since, until = f.time_bounds()
    assert until is None
    assert (datetime.now(UTC) - since).days >= 29


def test_parse_custom_range():
    f = parse_dashboard_filters(
        period_days=7,
        date_from="2026-01-01",
        date_to="2026-01-31",
        direction="inbound",
        operator_ids=[3, 1, 3],
    )
    assert f.direction == "inbound"
    assert f.operator_ids == (1, 3)
    since, until = f.time_bounds()
    assert since.date().isoformat() == "2026-01-01"
    assert until is not None
    assert until.date().isoformat() == "2026-01-31"


def test_parse_scenario_id():
    assert parse_dashboard_filters(scenario_id=5).scenario_id == 5
    assert parse_dashboard_filters(scenario_id=0).scenario_id is None
    assert parse_dashboard_filters().scenario_id is None
