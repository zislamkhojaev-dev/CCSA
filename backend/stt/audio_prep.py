"""Normalize audio to 16 kHz 16-bit PCM before ASR."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TARGET_SR = 16000
TARGET_WIDTH = 2  # 16-bit


def prepare_segment(seg, *, mono: bool = False):
    """Resample to 16 kHz / 16-bit and apply a light peak normalize."""
    if mono and getattr(seg, "channels", 1) != 1:
        seg = seg.set_channels(1)
    if getattr(seg, "frame_rate", TARGET_SR) != TARGET_SR:
        seg = seg.set_frame_rate(TARGET_SR)
    if getattr(seg, "sample_width", TARGET_WIDTH) != TARGET_WIDTH:
        seg = seg.set_sample_width(TARGET_WIDTH)
    try:
        peak = seg.max_dBFS
        if peak != float("-inf"):
            if peak < -24:
                seg = seg.apply_gain(min(12.0, -18.0 - peak))
            elif peak > -0.5:
                seg = seg.apply_gain(-3.0 - peak)
    except Exception as e:
        logger.debug("Peak normalize skipped: %s", e)
    return seg
