from app.services.call_utils import (
    duration_seconds_from_transcription,
    duration_seconds_from_utterances,
    effective_duration_seconds,
)


def test_duration_from_channels():
    trans = {
        "channels": {
            "client": {"duration_sec": 120.4},
            "agent": {"duration_sec": 118.2},
        }
    }
    assert duration_seconds_from_transcription(trans) == 120


def test_duration_from_utterances():
    utterances = [
        {"start": 0.0, "end": 12.5, "text": "hello"},
        {"start": 12.5, "end": 45.8, "text": "world"},
    ]
    assert duration_seconds_from_utterances(utterances) == 46


def test_duration_prefers_channels():
    trans = {
        "channels": {"mixed": {"duration_sec": 90.0}},
        "utterances": [{"start": 0, "end": 10, "text": "x"}],
    }
    assert duration_seconds_from_transcription(trans) == 90


def test_effective_duration_prefers_call_column():
    assert effective_duration_seconds(42, [{"start": 0, "end": 10}]) == 42


def test_effective_duration_from_utterances():
    utterances = [{"start": 0, "end": 30, "text": "hi"}]
    assert effective_duration_seconds(None, utterances) == 30
