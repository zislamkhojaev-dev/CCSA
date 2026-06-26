"""Helpers for call metadata derived from transcription payloads."""

from __future__ import annotations

from typing import Any


def duration_seconds_from_transcription(trans: dict | None) -> int | None:
    """Extract duration in whole seconds from an STT / stored transcription dict."""
    if not trans:
        return None

    channels = trans.get("channels")
    if isinstance(channels, dict):
        secs: list[float] = []
        for key in ("client", "agent", "mixed"):
            ch = channels.get(key)
            if isinstance(ch, dict):
                raw = ch.get("duration_sec")
                if isinstance(raw, (int, float)) and raw > 0:
                    secs.append(float(raw))
        if secs:
            return int(round(max(secs)))

    return duration_seconds_from_utterances(trans.get("utterances"))


def duration_seconds_from_utterances(utterances: Any) -> int | None:
    if not isinstance(utterances, list):
        return None
    ends: list[float] = []
    for u in utterances:
        if not isinstance(u, dict):
            continue
        end = u.get("end", u.get("start"))
        if isinstance(end, (int, float)) and end >= 0:
            ends.append(float(end))
    if not ends:
        return None
    return int(round(max(ends)))


def effective_duration_seconds(
    call_duration: int | None,
    utterances: Any = None,
    transcription: dict | None = None,
) -> int | None:
    """Resolve call duration from stored column or transcription payload."""
    if call_duration is not None:
        return int(call_duration)
    if transcription is not None:
        from_trans = duration_seconds_from_transcription(transcription)
        if from_trans is not None:
            return from_trans
    return duration_seconds_from_utterances(utterances)
