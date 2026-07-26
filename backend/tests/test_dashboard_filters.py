"""Dashboard filter parsing and SQL filter application."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Call
from app.services.dashboard_export import build_filter_summary, dashboard_export_filename
from app.services.dashboard_filters import apply_call_filters, parse_dashboard_filters


def test_parse_preset_period():
    f = parse_dashboard_filters(period_days=30)
    since, until = f.time_bounds()
    assert until is None
    assert (datetime.now(UTC) - since).days >= 29


def test_parse_custom_range_and_operators():
    f = parse_dashboard_filters(
        period_days=7,
        date_from="2026-01-01",
        date_to="2026-01-31",
        direction="inbound",
        operator_ids=[3, 1, 3, 0, -1],
    )
    assert f.direction == "inbound"
    assert f.operator_ids == (1, 3)
    since, until = f.time_bounds()
    assert since.date().isoformat() == "2026-01-01"
    assert until is not None
    assert until.date().isoformat() == "2026-01-31"


def test_parse_invalid_direction_dropped():
    assert parse_dashboard_filters(direction="sideways").direction is None
    assert parse_dashboard_filters(direction="  ").direction is None


def test_parse_scenario_id():
    assert parse_dashboard_filters(scenario_id=5).scenario_id == 5
    assert parse_dashboard_filters(scenario_id=0).scenario_id is None
    assert parse_dashboard_filters().scenario_id is None


def test_swapped_date_range_normalized():
    f = parse_dashboard_filters(date_from="2026-02-10", date_to="2026-02-01")
    since, until = f.time_bounds()
    assert since.date().isoformat() == "2026-02-01"
    assert until.date().isoformat() == "2026-02-10"


def test_to_dict_includes_effective_bounds():
    f = parse_dashboard_filters(period_days=14, direction="outbound")
    d = f.to_dict()
    assert d["period_days"] == 14
    assert d["direction"] == "outbound"
    assert d["effective_since"]
    assert d["effective_until"] is None


def test_apply_call_filters_compiles():
    f = parse_dashboard_filters(
        date_from="2026-01-01",
        date_to="2026-01-31",
        direction="inbound",
        operator_ids=[1, 2],
        scenario_id=9,
    )
    q = apply_call_filters(select(Call.id), f)
    compiled = str(q).lower()
    assert "direction" in compiled
    assert "operator_id" in compiled
    assert "scenario_id" in compiled


def test_filter_summary_period_and_scenario():
    f = parse_dashboard_filters(period_days=7, scenario_id=3)
    summary = build_filter_summary(f, scenario_name="Входящие")
    assert summary["period"] == "7 дней"
    assert summary["scenario"] == "Входящие"
    assert [x["key"] for x in summary["labels"]] == ["period", "scenario"]


def test_dashboard_export_filename():
    assert dashboard_export_filename(ext="json").startswith("dashboard-")
    assert dashboard_export_filename(ext="csv").endswith(".csv")
