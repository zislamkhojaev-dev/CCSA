from stt.diarization import (
    DiarSegment,
    assign_speaker_to_interval,
    assign_speakers_to_utterances,
    assign_speakers_to_words,
    overlap_seconds,
)
from stt.utterance_utils import group_words_to_utterances


def test_overlap_seconds():
    assert overlap_seconds(0, 5, 3, 8) == 2.0
    assert overlap_seconds(0, 2, 5, 10) == 0.0


def test_assign_speaker_by_overlap():
    diar = [
        DiarSegment(0.0, 3.0, "SPEAKER_00"),
        DiarSegment(3.0, 8.0, "SPEAKER_01"),
    ]
    role_map = {"SPEAKER_00": "agent", "SPEAKER_01": "client"}
    assert assign_speaker_to_interval(0.5, 2.0, diar, role_map) == "agent"
    assert assign_speaker_to_interval(4.0, 6.0, diar, role_map) == "client"


def test_assign_speakers_to_utterances():
    diar = [
        DiarSegment(0.0, 2.0, "A"),
        DiarSegment(2.0, 5.0, "B"),
    ]
    raw = [
        {"speaker": "mixed", "text": "hello", "start": 0.0, "end": 1.5},
        {"speaker": "mixed", "text": "world", "start": 2.5, "end": 4.0},
    ]
    out = assign_speakers_to_utterances(raw, diar, {"A": "client", "B": "agent"})
    assert out[0]["speaker"] == "client"
    assert out[1]["speaker"] == "agent"


def test_assign_speakers_to_words_splits_mid_segment():
    diar = [
        DiarSegment(0.0, 1.0, "A"),
        DiarSegment(1.0, 3.0, "B"),
    ]
    words = [
        {"text": "hello", "start": 0.2, "end": 0.6},
        {"text": "world", "start": 1.2, "end": 1.8},
    ]
    out = assign_speakers_to_words(words, diar, {"A": "client", "B": "agent"})
    utterances = group_words_to_utterances(out)
    assert len(utterances) == 2
    assert utterances[0]["speaker"] == "client"
    assert utterances[1]["speaker"] == "agent"


def test_group_words_to_utterances_merges_same_speaker():
    words = [
        {"text": "salom", "start": 0.0, "end": 0.4, "speaker": "client"},
        {"text": "mijoz", "start": 0.5, "end": 0.9, "speaker": "client"},
        {"text": "ha", "start": 1.2, "end": 1.4, "speaker": "agent"},
    ]
    out = group_words_to_utterances(words)
    assert len(out) == 2
    assert out[0]["text"] == "salom mijoz"
    assert out[1]["text"] == "ha"
