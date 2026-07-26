"""Stereo merge: channel is the speaker; RMS only drops cross-channel bleed."""

from __future__ import annotations

import pytest

from stt.stereo_utils import _is_duplicate_overlap, merge_stereo_utterances, merge_stereo_words

pydub = pytest.importorskip("pydub")
from pydub import AudioSegment  # noqa: E402
from pydub.generators import Sine  # noqa: E402


def _export_pair(tmp_path, client: AudioSegment, agent: AudioSegment) -> tuple[str, str]:
    client_path = tmp_path / "client.wav"
    agent_path = tmp_path / "agent.wav"
    client.export(client_path, format="wav")
    agent.export(agent_path, format="wav")
    return str(client_path), str(agent_path)


def test_duplicate_overlap_detected():
    existing = [
        {"speaker": "agent", "text": "assalomu alaykum", "start": 0.0, "end": 2.0},
    ]
    assert _is_duplicate_overlap(existing, "assalomu alaykum", 0.1, 1.8, "client") is True
    assert _is_duplicate_overlap(existing, "boshqa gap", 0.1, 1.8, "client") is False


def test_merge_keeps_channel_role_and_drops_bleed(tmp_path):
    """Louder client copy of bleed wins; role stays client (never relabeled)."""
    client = Sine(440).to_audio_segment(duration=2000).apply_gain(-3)
    client = client + AudioSegment.silent(duration=3000)
    # Quiet bleed on agent during client speech, then real agent speech
    agent = (
        Sine(330).to_audio_segment(duration=2000).apply_gain(-25)
        + AudioSegment.silent(duration=1000)
        + Sine(330).to_audio_segment(duration=2000).apply_gain(-3)
    )

    client_path, agent_path = _export_pair(tmp_path, client, agent)

    client_u = [{"speaker": "client", "text": "salom mijoz", "start": 0.0, "end": 1.8}]
    agent_u = [
        {"speaker": "agent", "text": "salom mijoz", "start": 0.0, "end": 1.8},
        {"speaker": "agent", "text": "operator gapiradi", "start": 3.2, "end": 4.8},
    ]
    merged = merge_stereo_utterances(client_u, agent_u, client_path, agent_path)

    by_text = {u["text"]: u["speaker"] for u in merged}
    assert by_text["salom mijoz"] == "client"
    assert by_text["operator gapiradi"] == "agent"
    assert [u["speaker"] for u in merged].count("client") == 1


def test_merge_stereo_words_channel_trusted(tmp_path):
    client = Sine(440).to_audio_segment(duration=1500).apply_gain(-3)
    client = client + AudioSegment.silent(duration=2500)
    agent = AudioSegment.silent(duration=2500) + Sine(330).to_audio_segment(duration=1500).apply_gain(-3)

    client_path, agent_path = _export_pair(tmp_path, client, agent)

    client_words = [
        {"text": "salom", "start": 0.1, "end": 0.5},
        {"text": "mijoz", "start": 0.55, "end": 0.95},
    ]
    agent_words = [
        {"text": "salom", "start": 0.1, "end": 0.5},  # bleed of client word
        {"text": "operator", "start": 2.6, "end": 3.1},
        {"text": "gapiradi", "start": 3.15, "end": 3.55},
    ]
    merged = merge_stereo_words(client_words, agent_words, client_path, agent_path)
    speakers = [u["speaker"] for u in merged]
    assert speakers[0] == "client"
    assert "agent" in speakers
    assert any("salom" in (u.get("text") or "") for u in merged if u["speaker"] == "client")
