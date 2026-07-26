"""Pure helpers for calls CSV/JSON export."""

import json

from app.services.calls_export import (
    EXPORT_FIELDNAMES,
    calls_export_filename,
    encode_export_file,
    export_calls_json_bytes,
    export_calls_to_csv,
    parse_export_filters,
)


def test_calls_export_filename():
    assert calls_export_filename(ext="csv").startswith("calls-")
    assert calls_export_filename(ext="json").endswith(".json")


def test_parse_export_filters_dates_and_ops():
    kw = parse_export_filters(
        {
            "status_filter": "analyzed",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "score_op": "gt",
            "score_value": 50,
            "tag_id": 3,
        }
    )
    assert kw["status_filter"] == "analyzed"
    assert kw["date_from"].year == 2026
    assert kw["date_to"].hour == 23
    assert kw["score_op"] == "gt"
    assert kw["score_value"] == 50
    assert kw["tag_id"] == 3


def test_parse_export_filters_none():
    kw = parse_export_filters(None)
    assert kw["status_filter"] is None
    assert kw["date_from"] is None


def test_export_calls_csv_and_json():
    rows = [
        {
            "id": 1,
            "call_uuid": "u-1",
            "operator_name": "Ali",
            "direction": "inbound",
            "duration": 60,
            "client_number": "+99890",
            "call_timestamp": "2026-01-01T10:00:00",
            "status": "analyzed",
            "total_score": 80,
            "topic": "Заказ",
            "summary": "ok",
            "call_outcome": "resolved",
            "tags": "vip",
        }
    ]
    csv_text = export_calls_to_csv(rows)
    assert "operator_name" in csv_text
    assert "Ali" in csv_text
    for field in EXPORT_FIELDNAMES:
        assert field in csv_text.splitlines()[0]

    payload = json.loads(export_calls_json_bytes(rows).decode("utf-8"))
    assert payload["count"] == 1
    assert payload["calls"][0]["topic"] == "Заказ"


def test_encode_export_file_formats():
    rows = [{"id": 1, "call_uuid": "x", "operator_name": None, "direction": "inbound",
             "duration": 1, "client_number": None, "call_timestamp": None, "status": "queued",
             "total_score": None, "topic": None, "summary": None, "call_outcome": None, "tags": ""}]
    csv_bytes, csv_type, csv_name = encode_export_file(rows, "csv")
    assert csv_type.startswith("text/csv")
    assert csv_name.endswith(".csv")
    assert csv_bytes.startswith(b"\xef\xbb\xbf")

    json_bytes, json_type, json_name = encode_export_file(rows, "json")
    assert json_type.startswith("application/json")
    assert json_name.endswith(".json")
    assert b"exported_at" in json_bytes
