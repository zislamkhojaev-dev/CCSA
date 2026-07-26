from app.services.call_query import SORT_COLUMNS, build_calls_count_query, build_calls_list_query


def test_sort_columns_defined():
    assert "operator_name" in SORT_COLUMNS
    assert "total_score" in SORT_COLUMNS
    assert "call_timestamp" in SORT_COLUMNS or "created_at" in SORT_COLUMNS


def test_build_list_query_compiles():
    q = build_calls_list_query(
        operator_match="contains",
        operator_value="Ali",
        score_op="gt",
        score_value=50,
        sort_by="total_score",
        sort_order="desc",
    )
    compiled = str(q).lower()
    assert "operator" in compiled
    assert "total_score" in compiled


def test_build_list_query_with_tag_filter():
    q = build_calls_list_query(tag_id=3)
    compiled = str(q).lower()
    assert "call_tags" in compiled
    assert "tag_id" in compiled


def test_build_count_query_compiles():
    q = build_calls_count_query(client_match="eq", client_value="+99890")
    assert q is not None
    assert "99890" in str(q) or "client" in str(q).lower()
