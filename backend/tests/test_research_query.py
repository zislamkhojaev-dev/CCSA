from app.services.research_query import (
    build_research_calls_by_ids_query,
    build_research_count_query,
    build_research_calls_query,
)


def test_build_research_count_query_compiles():
    q = build_research_count_query(
        direction="inbound",
        operator_id=1,
    )
    compiled = str(q).lower()
    assert "transcriptions" in compiled or "call" in compiled


def test_build_research_calls_query_compiles():
    q = build_research_calls_query(
        direction="outbound",
        operator_id=2,
    )
    compiled = str(q).lower()
    assert "full_text" in compiled or "transcription" in compiled


def test_build_research_calls_query_orders_by_effective_timestamp():
    q = build_research_calls_query()
    compiled = str(q).lower()
    assert "coalesce" in compiled
    assert "call_timestamp" in compiled
    assert "created_at" in compiled


def test_build_research_calls_query_with_extended_filters():
    q = build_research_calls_query(
        queue="Sales",
        tag_id=1,
        score_op="gt",
        score_value=50,
    )
    compiled = str(q).lower()
    assert "team_name" in compiled
    assert "call_tags" in compiled
    assert "tag_id" in compiled
    assert "total_score" in compiled


def test_build_research_calls_by_ids_query_compiles():
    q = build_research_calls_by_ids_query([1, 2, 3])
    compiled = str(q).lower()
    assert "in (" in compiled
