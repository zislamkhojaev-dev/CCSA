"""Helpers for call metadata derived from transcription payloads."""

from __future__ import annotations

from typing import Any


def _iter_utterances(utterances: Any) -> list[dict]:
    if isinstance(utterances, list):
        return [u for u in utterances if isinstance(u, dict)]
    if isinstance(utterances, dict):
        inner = utterances.get("utterances")
        if isinstance(inner, list):
            return [u for u in inner if isinstance(u, dict)]
    return []


def _format_offset(start: Any) -> str | None:
    if not isinstance(start, (int, float)) or start < 0:
        return None
    total = int(start)
    return f"{total // 60:02d}:{total % 60:02d}"


def format_transcript_for_llm(full_text: str | None, utterances: Any = None) -> str:
    """Build LLM input with speaker roles and timestamps when utterances exist."""
    lines: list[str] = []
    for u in _iter_utterances(utterances):
        text = str(u.get("text") or "").strip()
        if not text:
            continue
        speaker = str(u.get("speaker") or "mixed").strip() or "mixed"
        stamp = _format_offset(u.get("start"))
        prefix = f"[{speaker} {stamp}]" if stamp else f"[{speaker}]"
        lines.append(f"{prefix} {text}")
    if lines:
        return "\n".join(lines)
    return (full_text or "").strip()


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
