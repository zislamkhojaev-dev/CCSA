from __future__ import annotations

import re
import unicodedata

import jiwer


def normalize_text(text: str) -> str:
    """Normalize transcription for WER/CER comparison."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def wer(reference: str, hypothesis: str) -> float:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return float(jiwer.wer(ref, hyp))


def cer(reference: str, hypothesis: str) -> float:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return float(jiwer.cer(ref, hyp))
