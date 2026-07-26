"""Quality thresholds and topic taxonomy config."""

from app.services.quality_settings import (
    DEFAULT_TAXONOMY,
    UNCLASSIFIED_TOPIC,
    QualityConfig,
    normalize_config,
    parse_topics,
)


def test_parse_topics_dedup_and_trim():
    topics = parse_topics('["Заказ", " заказ ", "Жалоба", ""]')
    assert topics == ["Заказ", "Жалоба"]


def test_parse_topics_invalid_falls_back():
    assert parse_topics("not json") == list(DEFAULT_TAXONOMY)
    assert parse_topics("{}") == list(DEFAULT_TAXONOMY)


def test_normalize_config_clamps_and_orders_thresholds():
    cfg = normalize_config(threshold_good=70, threshold_mid=90, target=120, topics=["A", "a", "B"])
    assert cfg.threshold_good == 70
    assert cfg.threshold_mid == 70
    assert cfg.target == 100
    assert cfg.topics == ["A", "B"]


def test_bucket():
    cfg = QualityConfig(threshold_good=80, threshold_mid=50)
    assert cfg.bucket(90) == "green"
    assert cfg.bucket(60) == "yellow"
    assert cfg.bucket(10) == "red"
    assert cfg.bucket(None) == "gray"


def test_unclassified_constant():
    assert UNCLASSIFIED_TOPIC
