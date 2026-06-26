"""Shared Hugging Face ASR pipeline setup for the benchmark."""

from __future__ import annotations

from typing import Any


def build_whisper_pipeline(
    model: Any,
    tokenizer: Any,
    feature_extractor: Any,
) -> Any:
    from transformers import pipeline

    return pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=tokenizer,
        feature_extractor=feature_extractor,
        device="cpu",
        chunk_length_s=30,
        stride_length_s=5,
        ignore_warning=True,
    )


def load_whisper_model(hf_id: str) -> tuple[Any, Any, Any]:
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    processor = AutoProcessor.from_pretrained(hf_id)
    try:
        model = AutoModelForSpeechSeq2Seq.from_pretrained(hf_id, dtype=torch.float32)
    except TypeError:
        model = AutoModelForSpeechSeq2Seq.from_pretrained(hf_id, torch_dtype=torch.float32)
    model.eval()
    return model, processor.tokenizer, processor.feature_extractor
