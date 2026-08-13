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


def test_effective_duration_from_transcription_when_column_missing():
    trans = {"channels": {"mixed": {"duration_sec": 55.0}}}
    assert effective_duration_seconds(None, None, transcription=trans) == 55


def test_format_transcript_for_llm_uses_speakers_and_timestamps():
    from app.services.call_utils import format_transcript_for_llm

    text = format_transcript_for_llm(
        "ignored",
        [
            {"speaker": "client", "start": 5, "text": "Salom"},
            {"speaker": "agent", "start": 72.4, "text": "Assalomu alaykum"},
        ],
    )
    assert text == "[client 00:05] Salom\n[agent 01:12] Assalomu alaykum"


def test_format_transcript_for_llm_falls_back_to_full_text():
    from app.services.call_utils import format_transcript_for_llm

    assert format_transcript_for_llm("plain text", []) == "plain text"
    assert format_transcript_for_llm("  hi  ", None) == "hi"
