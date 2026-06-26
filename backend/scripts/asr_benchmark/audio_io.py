"""Load mono 16 kHz audio and chunk for long-file ASR (MMS, etc.)."""

from __future__ import annotations

import numpy as np

TARGET_SR = 16_000
CHUNK_SEC = 30.0


def load_mono_resampled(path: str, target_sr: int = TARGET_SR) -> np.ndarray:
    import torch
    import torchaudio

    waveform, sr = torchaudio.load(path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if int(sr) != target_sr:
        waveform = torchaudio.functional.resample(waveform, int(sr), target_sr)
    return waveform.squeeze(0).numpy().astype(np.float32)


def iter_chunks(
    samples: np.ndarray,
    *,
    sr: int = TARGET_SR,
    chunk_sec: float = CHUNK_SEC,
) -> list[np.ndarray]:
    if samples.size == 0:
        return []
    chunk_len = max(1, int(chunk_sec * sr))
    return [samples[start : start + chunk_len] for start in range(0, len(samples), chunk_len)]
