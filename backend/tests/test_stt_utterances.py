from stt.utterance_utils import (
    chunks_to_utterances,
    group_words_to_utterances,
    merge_utterances,
    timestamps_degenerate,
    utterance_sort_key,
)


def test_merge_interleaves_by_start():
    client = [{"speaker": "client", "text": "salom", "start": 0.0, "end": 2.0}]
    agent = [{"speaker": "agent", "text": "assalom", "start": 1.5, "end": 4.0}]
    merged = merge_utterances(client, agent)
    assert [u["speaker"] for u in merged] == ["client", "agent"]


def test_merge_tie_breaker_speaker_then_end():
    client = [{"speaker": "client", "text": "a", "start": 0.0, "end": 1.0}]
    agent = [{"speaker": "agent", "text": "b", "start": 0.0, "end": 5.0}]
    merged = merge_utterances(client, agent)
    assert merged[0]["speaker"] == "client"
    assert merged[1]["speaker"] == "agent"


def test_chunks_without_timestamps_distributed_over_duration():
    chunks = [{"text": "one"}, {"text": "two"}, {"text": "three"}]
    utt = chunks_to_utterances(chunks, speaker="agent", duration_sec=30.0, time_offset=0.0)
    assert len(utt) == 3
    assert utt[0]["start"] == 0.0
    assert utt[1]["start"] == 10.0
    assert utt[2]["start"] == 20.0
    assert utt[-1]["end"] == 30.0


def test_timestamps_degenerate_single_blob():
    utt = [{"speaker": "agent", "text": "x" * 300, "start": 0.0, "end": 120.0}]
    assert timestamps_degenerate(utt, 120.0) is True


def test_sort_key_order():
    assert utterance_sort_key({"speaker": "client", "start": 0, "end": 1}) < utterance_sort_key(
        {"speaker": "agent", "start": 0, "end": 5}
    )
