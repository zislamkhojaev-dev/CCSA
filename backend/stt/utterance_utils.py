"""Pure helpers for STT utterance timestamps and merge (unit-testable)."""

from __future__ import annotations

import re
from typing import Any

SPEAKER_RANK = {"client": 0, "agent": 1, "mixed": 2}


def utterance_sort_key(u: dict) -> tuple:
    return (
        float(u.get("start", 0)),
        float(u.get("end", u.get("start", 0))),
        SPEAKER_RANK.get(u.get("speaker", "mixed"), 2),
    )


def merge_utterances(*lists: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for lst in lists:
        merged.extend(lst)
    merged.sort(key=utterance_sort_key)
    return merged


def finalize_utterances(utterances: list[dict]) -> list[dict]:
    utterances.sort(key=utterance_sort_key)
    return utterances


def to_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            pass
        if ":" in s:
            parts = s.split(":")
            try:
                nums = [float(p) for p in parts]
            except ValueError:
                return None
            if len(nums) == 3:
                return nums[0] * 3600 + nums[1] * 60 + nums[2]
            if len(nums) == 2:
                return nums[0] * 60 + nums[1]
    return None


def parse_chunk_timestamp(ts: Any) -> tuple[float | None, float | None] | None:
    if ts is None:
        return None
    if isinstance(ts, list) and ts:
        if isinstance(ts[0], (list, tuple)):
            starts: list[float] = []
            ends: list[float] = []
            for item in ts:
                if not isinstance(item, (list, tuple)) or not item:
                    continue
                st = to_seconds(item[0])
                en = to_seconds(item[1]) if len(item) > 1 else None
                if st is not None:
                    starts.append(st)
                if en is not None:
                    ends.append(en)
            if starts:
                return (min(starts), max(ends) if ends else None)
            return None
        if len(ts) >= 2:
            return (to_seconds(ts[0]), to_seconds(ts[1]))
    if isinstance(ts, (list, tuple)) and len(ts) >= 2:
        return (to_seconds(ts[0]), to_seconds(ts[1]))
    return None


def timestamps_degenerate(utterances: list[dict], duration_sec: float) -> bool:
    if not utterances:
        return False
    if len(utterances) == 1:
        u = utterances[0]
        span = float(u.get("end", 0)) - float(u.get("start", 0))
        text_len = len((u.get("text") or ""))
        return duration_sec > 25 and (span >= duration_sec * 0.85 or text_len > 200)
    starts = [round(float(u.get("start", 0)), 1) for u in utterances]
    unique_starts = len(set(starts))
    if unique_starts <= 1 and duration_sec > 10:
        return True
    if unique_starts <= max(2, len(utterances) // 4) and starts[0] < 1.0:
        return True
    return False


def slot_distribute_chunks(
    chunks: list[dict],
    *,
    speaker: str,
    duration_sec: float,
    time_offset: float,
) -> list[dict]:
    valid = [c for c in chunks if (c.get("text") or "").strip()]
    if not valid:
        return []
    slot = duration_sec / len(valid) if duration_sec > 0 else 1.0
    utterances: list[dict] = []
    for i, chunk in enumerate(valid):
        start = time_offset + i * slot
        end = time_offset + (i + 1) * slot
        utterances.append(
            {
                "speaker": speaker,
                "text": chunk["text"].strip(),
                "start": round(start, 2),
                "end": round(end, 2),
            }
        )
    return utterances


def split_monologue(
    text: str,
    *,
    speaker: str,
    duration_sec: float,
    time_offset: float,
) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?…;])\s+", text) if p.strip()]
    if len(parts) <= 1 and len(text) > 160:
        parts = [text[i : i + 120].strip() for i in range(0, len(text), 120) if text[i : i + 120].strip()]
    if len(parts) <= 1:
        end = time_offset + (duration_sec or 1.0)
        return [
            {
                "speaker": speaker,
                "text": text,
                "start": round(time_offset, 2),
                "end": round(end, 2),
            }
        ]
    slot = (duration_sec or 1.0) / len(parts)
    utterances: list[dict] = []
    for i, part in enumerate(parts):
        start = time_offset + i * slot
        end = time_offset + (i + 1) * slot
        utterances.append(
            {
                "speaker": speaker,
                "text": part,
                "start": round(start, 2),
                "end": round(end, 2),
            }
        )
    return utterances


def chunks_to_utterances(
    chunks: list[dict],
    *,
    speaker: str,
    duration_sec: float,
    time_offset: float,
) -> list[dict]:
    valid = [c for c in chunks if (c.get("text") or "").strip()]
    if not valid:
        return []

    parsed: list[tuple[dict, tuple[float | None, float | None] | None]] = []
    real_ts = 0
    for chunk in valid:
        ts = parse_chunk_timestamp(chunk.get("timestamp") or chunk.get("timestamps"))
        parsed.append((chunk, ts))
        if ts and ts[0] is not None and (ts[0] > 0.05 or (ts[1] is not None and ts[1] > ts[0])):
            real_ts += 1

    if real_ts < max(1, len(valid) // 3):
        return slot_distribute_chunks(valid, speaker=speaker, duration_sec=duration_sec, time_offset=time_offset)

    utterances: list[dict] = []
    prev_end = time_offset
    for i, (chunk, ts) in enumerate(parsed):
        text = chunk["text"].strip()
        if ts and ts[0] is not None:
            start = ts[0]
            end = ts[1]
            if end is None:
                if i + 1 < len(parsed) and parsed[i + 1][1] and parsed[i + 1][1][0] is not None:
                    end = parsed[i + 1][1][0]
                else:
                    end = duration_sec
        else:
            slot = duration_sec / len(valid) if duration_sec > 0 else 1.0
            start = i * slot
            end = (i + 1) * slot

        start += time_offset
        end = (end if end is not None else duration_sec) + time_offset
        if start < prev_end:
            start = prev_end
        if end <= start:
            end = start + 0.2
        utterances.append(
            {
                "speaker": speaker,
                "text": text,
                "start": round(start, 2),
                "end": round(end, 2),
            }
        )
        prev_end = end

    return utterances


def group_words_to_utterances(
    words: list[dict],
    *,
    max_gap_sec: float = 0.85,
) -> list[dict]:
    """Merge consecutive words from the same speaker into utterance segments."""
    if not words:
        return []

    ordered = sorted(words, key=lambda w: (float(w["start"]), float(w["end"])))
    utterances: list[dict] = []
    speaker = ordered[0]["speaker"]
    texts = [ordered[0]["text"].strip()]
    start = float(ordered[0]["start"])
    end = float(ordered[0]["end"])

    for word in ordered[1:]:
        text = (word.get("text") or "").strip()
        if not text:
            continue
        w_start = float(word["start"])
        w_end = float(word["end"])
        same_speaker = word["speaker"] == speaker
        gap = w_start - end
        if same_speaker and gap <= max_gap_sec:
            texts.append(text)
            end = max(end, w_end)
            continue

        utterances.append(
            {
                "speaker": speaker,
                "text": " ".join(texts),
                "start": round(start, 2),
                "end": round(end, 2),
            }
        )
        speaker = word["speaker"]
        texts = [text]
        start = w_start
        end = w_end

    utterances.append(
        {
            "speaker": speaker,
            "text": " ".join(texts),
            "start": round(start, 2),
            "end": round(end, 2),
        }
    )
    return utterances


def enforce_monotonic(utterances: list[dict]) -> list[dict]:
    if not utterances:
        return utterances
    prev_end = float(utterances[0].get("start", 0))
    for u in utterances:
        start = float(u["start"])
        end = float(u.get("end", start))
        if start < prev_end:
            start = prev_end
            u["start"] = round(start, 2)
        if end <= start:
            end = start + 0.2
            u["end"] = round(end, 2)
        prev_end = end
    return utterances
