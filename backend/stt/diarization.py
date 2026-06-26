"""Speaker diarization (pyannote) and assignment to ASR segments."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

DiarizationMethod = Literal["pyannote", "stereo_channels", "mono"]
RoleSpeaker = Literal["client", "agent", "mixed"]

_diarization_pipeline: Any = None
_diarization_load_error: str | None = None


@dataclass(frozen=True)
class DiarSegment:
    start: float
    end: float
    label: str


def overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speaker_to_interval(
    start: float,
    end: float,
    diar_segments: list[DiarSegment],
    label_to_role: dict[str, RoleSpeaker],
) -> RoleSpeaker:
    best_label: str | None = None
    best_overlap = 0.0
    for seg in diar_segments:
        ov = overlap_seconds(start, end, seg.start, seg.end)
        if ov > best_overlap:
            best_overlap = ov
            best_label = seg.label
    if best_label is None:
        return "mixed"
    return label_to_role.get(best_label, "mixed")


def assign_speakers_to_utterances(
    utterances: list[dict],
    diar_segments: list[DiarSegment],
    label_to_role: dict[str, RoleSpeaker],
) -> list[dict]:
    out: list[dict] = []
    for u in utterances:
        role = assign_speaker_to_interval(
            float(u["start"]),
            float(u["end"]),
            diar_segments,
            label_to_role,
        )
        out.append({**u, "speaker": role})
    return out


def assign_speakers_to_words(
    words: list[dict],
    diar_segments: list[DiarSegment],
    label_to_role: dict[str, RoleSpeaker],
) -> list[dict]:
    """Assign client/agent per word using diarization overlap (word-level precision)."""
    out: list[dict] = []
    for w in words:
        start = float(w["start"])
        end = float(w.get("end", start))
        if end <= start:
            end = start + 0.05
        role = assign_speaker_to_interval(start, end, diar_segments, label_to_role)
        out.append({**w, "speaker": role})
    return out


def _load_pyannote_pipeline() -> Any:
    global _diarization_pipeline, _diarization_load_error
    if _diarization_pipeline is not None:
        return _diarization_pipeline
    if _diarization_load_error is not None:
        raise RuntimeError(_diarization_load_error)

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if not token:
        _diarization_load_error = "HF_TOKEN is required for pyannote diarization"
        raise RuntimeError(_diarization_load_error)

    model_id = os.getenv("STT_PYANNOTE_MODEL", "pyannote/speaker-diarization-3.1")
    try:
        from pyannote.audio import Pipeline

        logger.info("Loading pyannote pipeline %s", model_id)
        try:
            _diarization_pipeline = Pipeline.from_pretrained(model_id, token=token)
        except TypeError:
            _diarization_pipeline = Pipeline.from_pretrained(model_id, use_auth_token=token)
        return _diarization_pipeline
    except Exception as e:
        _diarization_load_error = str(e)
        logger.exception("Failed to load pyannote pipeline")
        raise


def run_pyannote_diarization(audio_path: str) -> list[DiarSegment]:
    pipeline = _load_pyannote_pipeline()
    device = os.getenv("STT_PYANNOTE_DEVICE", "cpu")
    if hasattr(pipeline, "to"):
        import torch

        if device == "cuda" and torch.cuda.is_available():
            pipeline = pipeline.to(torch.device("cuda"))
        else:
            pipeline = pipeline.to(torch.device("cpu"))

    min_speakers = int(os.getenv("STT_DIARIZATION_MIN_SPEAKERS", "2"))
    max_speakers = int(os.getenv("STT_DIARIZATION_MAX_SPEAKERS", "2"))
    diarization = pipeline(
        audio_path,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )

    segments: list[DiarSegment] = []
    for turn, _track, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            DiarSegment(
                start=float(turn.start),
                end=float(turn.end),
                label=str(speaker),
            )
        )
    segments.sort(key=lambda s: (s.start, s.end))
    return segments


def map_labels_to_roles(
    diar_segments: list[DiarSegment],
    *,
    stereo_client_path: str | None = None,
    stereo_agent_path: str | None = None,
) -> dict[str, RoleSpeaker]:
    """Map pyannote labels (SPEAKER_00, …) to client/agent using stereo energy when possible."""
    labels = sorted({s.label for s in diar_segments})
    if len(labels) < 2:
        return {labels[0]: "agent"} if labels else {}

    if stereo_client_path and stereo_agent_path:
        try:
            from pydub import AudioSegment

            client_seg = AudioSegment.from_file(stereo_client_path)
            agent_seg = AudioSegment.from_file(stereo_agent_path)
            label_scores: dict[str, tuple[float, float]] = {lb: (0.0, 0.0) for lb in labels}

            for seg in diar_segments:
                start_ms = int(seg.start * 1000)
                end_ms = int(seg.end * 1000)
                c_slice = client_seg[start_ms:end_ms]
                a_slice = agent_seg[start_ms:end_ms]
                label_scores[seg.label] = (
                    label_scores[seg.label][0] + c_slice.rms,
                    label_scores[seg.label][1] + a_slice.rms,
                )

            ranked = sorted(
                labels,
                key=lambda lb: label_scores[lb][1] - label_scores[lb][0],
                reverse=True,
            )
            return {ranked[0]: "agent", ranked[1]: "client"}
        except Exception as e:
            logger.warning("Stereo-based role mapping failed: %s", e)

    default_agent = os.getenv("STT_DEFAULT_AGENT_LABEL", labels[0])
    mapping: dict[str, RoleSpeaker] = {}
    for lb in labels:
        mapping[lb] = "agent" if lb == default_agent else "client"
    if len(labels) == 2 and all(v == "agent" for v in mapping.values()):
        mapping[labels[1]] = "client"
    return mapping


def diarization_available() -> bool:
    return bool(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"))


def get_diarization_method(requested: str | None = None) -> DiarizationMethod:
    raw = (requested or os.getenv("STT_DIARIZATION_METHOD", "stereo_channels")).strip().lower()
    if raw == "pyannote":
        return "pyannote"
    if raw in ("stereo_channels", "stereo", "channels"):
        return "stereo_channels"
    if raw == "mono":
        return "mono"
    return "stereo_channels"
