"""Stereo call recordings: channel split, mapping, cross-talk cleanup."""

from __future__ import annotations

import logging
import os
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any

from stt.utterance_utils import group_words_to_utterances

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _slice_rms(seg: Any, start_sec: float, end_sec: float) -> float:
    start_ms = max(0, int(start_sec * 1000))
    end_ms = max(start_ms + 1, int(end_sec * 1000))
    piece = seg[start_ms:end_ms]
    if len(piece) < 1:
        return 0.0
    return float(piece.rms)


def split_stereo_to_channels(audio_bytes: bytes) -> tuple[bytes | None, bytes | None, str]:
    """
    Split stereo WAV/MP3 into client and agent mono WAV bytes.
    Mapping: STT_CLIENT_CHANNEL=left|right (default left → client).
    """
    from pydub import AudioSegment

    from stt.audio_prep import prepare_segment

    seg = AudioSegment.from_file(BytesIO(audio_bytes))
    if seg.channels < 2:
        return None, None, "mono"

    channels = seg.split_to_mono()
    left, right = channels[0], channels[1]
    client_is_left = os.getenv("STT_CLIENT_CHANNEL", "left").strip().lower() != "right"
    if client_is_left:
        client_ch, agent_ch = left, right
        mapping = "left=client, right=agent"
    else:
        client_ch, agent_ch = right, left
        mapping = "right=client, left=agent"

    client_ch = prepare_segment(client_ch, mono=True)
    agent_ch = prepare_segment(agent_ch, mono=True)
    buf_client, buf_agent = BytesIO(), BytesIO()
    client_ch.export(buf_client, format="wav")
    agent_ch.export(buf_agent, format="wav")
    return buf_client.getvalue(), buf_agent.getvalue(), mapping


def merge_stereo_utterances(
    client_utterances: list[dict],
    agent_utterances: list[dict],
    client_audio_path: str,
    agent_audio_path: str,
) -> list[dict]:
    """
    Combine the two per-channel ASR passes into a single timeline.

    For true stereo recordings the channel *is* the speaker, so the role is taken
    from the channel of origin (client channel → client, agent channel → agent)
    and is never re-decided by energy. RMS / text similarity are used only to drop
    cross-channel bleed — the same words leaking into the other channel.
    """
    from pydub import AudioSegment

    client_seg = AudioSegment.from_file(client_audio_path)
    agent_seg = AudioSegment.from_file(agent_audio_path)

    min_rms = _env_int("STT_STEREO_MIN_RMS", 80)
    min_text_len = _env_int("STT_STEREO_MIN_TEXT_LEN", 2)

    tagged: list[tuple[dict, str]] = []
    for u in client_utterances:
        if (u.get("text") or "").strip():
            tagged.append((u, "client"))
    for u in agent_utterances:
        if (u.get("text") or "").strip():
            tagged.append((u, "agent"))
    tagged.sort(key=lambda x: (float(x[0].get("start", 0)), float(x[0].get("end", 0))))

    merged: list[dict] = []

    for u, source in tagged:
        text = (u.get("text") or "").strip()
        if len(text) < min_text_len:
            continue

        start = float(u.get("start", 0))
        end = float(u.get("end", start + 0.1))
        if end <= start:
            end = start + 0.15

        own_rms = _slice_rms(client_seg if source == "client" else agent_seg, start, end)
        other_rms = _slice_rms(agent_seg if source == "client" else client_seg, start, end)

        # No real speech in either channel here.
        if own_rms < min_rms and other_rms < min_rms:
            continue
        # Source channel is silent while the other is clearly louder → this line is
        # bleed of the other speaker leaking into the source channel. Drop it.
        if own_rms < min_rms and other_rms > own_rms * 1.5:
            continue

        # Same words transcribed on both channels (bleed duplicate): keep only the
        # copy from the louder channel, which is the real speaker. The survivor
        # keeps its own channel's role — we never relabel genuine speech.
        dup_idx = _find_cross_channel_duplicate(merged, text, start, end, source)
        if dup_idx is not None:
            prev = merged[dup_idx]
            prev_seg = client_seg if prev["speaker"] == "client" else agent_seg
            prev_rms = _slice_rms(prev_seg, float(prev["start"]), float(prev["end"]))
            if own_rms > prev_rms:
                merged[dup_idx] = {
                    "speaker": source,
                    "text": text,
                    "start": round(start, 2),
                    "end": round(end, 2),
                }
            continue

        merged.append(
            {
                "speaker": source,
                "text": text,
                "start": round(start, 2),
                "end": round(end, 2),
            }
        )

    merged.sort(key=lambda x: (x["start"], x["end"]))
    logger.info(
        "Stereo merge (channel-trusted): client_in=%s agent_in=%s out=%s",
        len(client_utterances),
        len(agent_utterances),
        len(merged),
    )
    return merged


def merge_stereo_words(
    client_words: list[dict],
    agent_words: list[dict],
    client_audio_path: str,
    agent_audio_path: str,
) -> list[dict]:
    """
    Word-level stereo merge.

    The speaker of every word is taken from its channel of origin; energy is used
    only to drop cross-channel bleed (the same word leaking into the other
    channel, kept from the louder side). Consecutive same-speaker words are then
    grouped into utterances.
    """
    from pydub import AudioSegment

    client_seg = AudioSegment.from_file(client_audio_path)
    agent_seg = AudioSegment.from_file(agent_audio_path)

    min_rms = _env_int("STT_STEREO_MIN_RMS", 80)

    tagged: list[tuple[dict, str]] = []
    for w in client_words:
        if (w.get("text") or "").strip():
            tagged.append((w, "client"))
    for w in agent_words:
        if (w.get("text") or "").strip():
            tagged.append((w, "agent"))
    tagged.sort(key=lambda x: (float(x[0]["start"]), float(x[0]["end"])))

    # Drop cross-channel bleed duplicates, keeping the louder channel's copy.
    # Same-channel words are never deduped against each other (a speaker may repeat
    # a word) — only the opposite channel is treated as potential bleed.
    deduped: list[tuple[dict, str]] = []
    for word, source in tagged:
        text = word["text"].strip()
        start = float(word["start"])
        end = float(word.get("end", start))
        if end <= start:
            end = start + 0.05

        replaced = False
        low = max(0, len(deduped) - 8)
        for idx in range(len(deduped) - 1, low - 1, -1):
            prev_word, prev_source = deduped[idx]
            if prev_source == source:
                continue
            prev_start = float(prev_word["start"])
            prev_end = float(prev_word.get("end", prev_start))
            overlap = min(end, prev_end) - max(start, prev_start)
            if overlap < 0.08:
                continue
            ratio = SequenceMatcher(
                None, text.lower(), (prev_word.get("text") or "").lower()
            ).ratio()
            if ratio < 0.65:
                continue

            src_seg = client_seg if source == "client" else agent_seg
            prev_seg = client_seg if prev_source == "client" else agent_seg
            src_rms = _slice_rms(src_seg, start, end)
            prev_rms = _slice_rms(prev_seg, prev_start, prev_end)
            if src_rms > prev_rms:
                deduped[idx] = (word, source)
            replaced = True
            break
        if not replaced:
            deduped.append((word, source))

    # Role = channel of origin. RMS only drops bleed/silence, never relabels.
    labeled: list[dict] = []
    for word, source in deduped:
        text = word["text"].strip()
        start = float(word["start"])
        end = float(word.get("end", start))
        if end <= start:
            end = start + 0.05

        own_rms = _slice_rms(client_seg if source == "client" else agent_seg, start, end)
        other_rms = _slice_rms(agent_seg if source == "client" else client_seg, start, end)

        if own_rms < min_rms and other_rms < min_rms:
            continue
        if own_rms < min_rms and other_rms > own_rms * 1.5:
            continue

        labeled.append(
            {
                "text": text,
                "start": round(start, 2),
                "end": round(end, 2),
                "speaker": source,
            }
        )

    merged = group_words_to_utterances(labeled)
    logger.info(
        "Stereo word merge (channel-trusted): client_words=%s agent_words=%s labeled=%s utterances=%s",
        len(client_words),
        len(agent_words),
        len(labeled),
        len(merged),
    )
    return merged


def _find_cross_channel_duplicate(
    existing: list[dict],
    text: str,
    start: float,
    end: float,
    speaker: str,
) -> int | None:
    """
    Index of a recent opposite-channel line overlapping in time with similar text
    (i.e. the same speech bled into both channels), or None if there is no match.
    """
    low = max(0, len(existing) - 8)
    for idx in range(len(existing) - 1, low - 1, -1):
        prev = existing[idx]
        if prev["speaker"] == speaker:
            continue
        ov = min(end, float(prev["end"])) - max(start, float(prev["start"]))
        if ov < 0.35:
            continue
        ratio = SequenceMatcher(None, text.lower(), (prev["text"] or "").lower()).ratio()
        if ratio > 0.55:
            return idx
        if len(text) < 24 and ov > 0.5:
            return idx
    return None


def _is_duplicate_overlap(
    existing: list[dict],
    text: str,
    start: float,
    end: float,
    speaker: str,
) -> bool:
    """Backward-compatible bool wrapper around _find_cross_channel_duplicate."""
    return _find_cross_channel_duplicate(existing, text, start, end, speaker) is not None
