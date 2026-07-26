"""Operator extraction from Webitel history payloads."""

from app.services.operator_sync import OPERATOR_LOOKBACK_DAYS, extract_operators, operator_lookback_start


def test_extract_operators_unique_first_seen():
    items = [
        {"agent_id": "10", "agent_name": "Ali"},
        {"user_id": "10", "user_name": "Ali Duplicate"},
        {"agent_id": "11", "agent_name": "Bob"},
        {"agent_id": "", "agent_name": "Skip"},
        {"agent_id": "12", "agent_name": ""},
    ]
    assert extract_operators(items) == [("10", "Ali"), ("11", "Bob")]


def test_operator_lookback_start_is_recent():
    start = operator_lookback_start()
    assert OPERATOR_LOOKBACK_DAYS == 7
    assert start.year >= 2020
