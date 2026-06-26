from stt.stereo_utils import _is_duplicate_overlap, merge_stereo_utterances, merge_stereo_words


def test_duplicate_overlap_detected():
    existing = [
        {"speaker": "agent", "text": "assalomu alaykum", "start": 0.0, "end": 2.0},
    ]
    assert _is_duplicate_overlap(existing, "assalomu alaykum", 0.1, 1.8, "client") is True


def test_merge_prefers_louder_channel(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("pydub")
    from pydub import AudioSegment
    from pydub.generators import Sine

    client = Sine(440).to_audio_segment(duration=2000).apply_gain(-6)
    client = client + AudioSegment.silent(duration=3000)
    agent = AudioSegment.silent(duration=3000) + Sine(330).to_audio_segment(duration=2000).apply_gain(-6)

    client_path = tmp_path / "client.wav"
    agent_path = tmp_path / "agent.wav"
    client.export(client_path, format="wav")
    agent.export(agent_path, format="wav")

    client_u = [{"speaker": "client", "text": "salom mijoz", "start": 0.0, "end": 1.8}]
    agent_u = [
        {"speaker": "agent", "text": "salom mijoz", "start": 0.0, "end": 1.8},
        {"speaker": "agent", "text": "operator gapiradi", "start": 3.2, "end": 4.8},
    ]
    merged = merge_stereo_utterances(client_u, agent_u, str(client_path), str(agent_path))
    speakers = [u["speaker"] for u in merged]
    assert "client" in speakers
    assert speakers.count("agent") >= 1
    assert not (speakers[0] == "agent" and merged[0]["text"] == "salom mijoz")


def test_merge_stereo_words_prefers_louder_channel(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("pydub")
    from pydub import AudioSegment
    from pydub.generators import Sine

    client = Sine(440).to_audio_segment(duration=1500).apply_gain(-6)
    client = client + AudioSegment.silent(duration=2500)
    agent = AudioSegment.silent(duration=2500) + Sine(330).to_audio_segment(duration=1500).apply_gain(-6)

    client_path = tmp_path / "client.wav"
    agent_path = tmp_path / "agent.wav"
    client.export(client_path, format="wav")
    agent.export(agent_path, format="wav")

    client_words = [
        {"text": "salom", "start": 0.1, "end": 0.5},
        {"text": "mijoz", "start": 0.55, "end": 0.95},
    ]
    agent_words = [
        {"text": "salom", "start": 0.1, "end": 0.5},
        {"text": "operator", "start": 2.6, "end": 3.1},
        {"text": "gapiradi", "start": 3.15, "end": 3.55},
    ]
    merged = merge_stereo_words(
        client_words, agent_words, str(client_path), str(agent_path)
    )
    speakers = [u["speaker"] for u in merged]
    assert "client" in speakers
    assert "agent" in speakers
    assert speakers[0] == "client"
