from __future__ import annotations

import gc
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import psutil

from scripts.asr_benchmark.audio_io import iter_chunks, load_mono_resampled
from scripts.asr_benchmark.config import MMS_UZ_TARGET_LANG, ModelSpec
from scripts.asr_benchmark.transformers_int8 import load_transformers_int8_pipeline
from scripts.asr_benchmark.transformers_pipe import build_whisper_pipeline, load_whisper_model

LANGUAGE = "uz"
TEMPERATURE = 0.0


@dataclass
class TranscribeResult:
    text: str
    duration_sec: float
    peak_rss_bytes: int


def _monitor_peak_rss(stop: threading.Event, peak: list[int]) -> None:
    proc = psutil.Process()
    while not stop.is_set():
        peak[0] = max(peak[0], proc.memory_info().rss)
        stop.wait(0.05)


def measure(fn: Callable[[], str]) -> tuple[str, float, int]:
    gc.collect()
    proc = psutil.Process()
    baseline = proc.memory_info().rss
    peak = [baseline]
    stop = threading.Event()
    monitor = threading.Thread(target=_monitor_peak_rss, args=(stop, peak), daemon=True)
    monitor.start()
    t0 = time.perf_counter()
    text = fn()
    duration = time.perf_counter() - t0
    stop.set()
    monitor.join(timeout=1.0)
    return text, duration, peak[0]


class ModelRunner:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self._model: Any = None
        self.session_peak_rss = 0

    def load(self) -> None:
        if self._model is not None:
            return

        peak = [0]
        stop = threading.Event()
        monitor = threading.Thread(target=_monitor_peak_rss, args=(stop, peak), daemon=True)
        monitor.start()
        try:
            if self.spec.engine == "transformers":
                self._model = _load_transformers(self.spec)
            elif self.spec.engine == "ct2":
                self._model = _load_ct2(self.spec.ct2_path or "", self.spec.compute_type or "int8")
            elif self.spec.engine == "qwen_asr":
                self._model = _load_qwen_asr(self.spec)
            elif self.spec.engine == "mms":
                self._model = _load_mms(self.spec)
            else:
                raise ValueError(f"Unknown engine: {self.spec.engine}")
        finally:
            stop.set()
            monitor.join(timeout=1.0)
            self.session_peak_rss = max(self.session_peak_rss, peak[0])

    def unload(self) -> None:
        self._model = None
        self.session_peak_rss = 0
        gc.collect()

    def transcribe_file(self, audio_path: str) -> TranscribeResult:
        self.load()

        def _run() -> str:
            if self.spec.engine == "transformers":
                return _transcribe_transformers(self._model, audio_path)
            if self.spec.engine == "ct2":
                return _transcribe_ct2(self._model, audio_path)
            if self.spec.engine == "qwen_asr":
                return _transcribe_qwen_asr(self._model, audio_path)
            return _transcribe_mms(self._model, audio_path)

        text, duration, peak_rss = measure(_run)
        self.session_peak_rss = max(self.session_peak_rss, peak_rss)
        return TranscribeResult(text=text, duration_sec=duration, peak_rss_bytes=peak_rss)


def _load_transformers(spec: ModelSpec) -> Any:
    if spec.transformers_path:
        return load_transformers_int8_pipeline(spec.transformers_path)

    hf_id = spec.hf_id or ""
    model, tokenizer, feature_extractor = load_whisper_model(hf_id)
    return build_whisper_pipeline(model, tokenizer, feature_extractor)


def _transcribe_transformers(pipe: Any, audio_path: str) -> str:
    result = pipe(
        audio_path,
        return_timestamps=False,
        generate_kwargs={
            "task": "transcribe",
            "language": LANGUAGE,
            "temperature": TEMPERATURE,
            "num_beams": 1,
        },
    )
    return (result.get("text") or "").strip()


def _load_ct2(model_path: str, compute_type: str) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(model_path, device="cpu", compute_type=compute_type)


def _transcribe_ct2(model: Any, audio_path: str) -> str:
    segments, _info = model.transcribe(
        audio_path,
        language=LANGUAGE,
        temperature=TEMPERATURE,
        beam_size=5,
        vad_filter=True,
        word_timestamps=False,
        condition_on_previous_text=False,
    )
    parts = [seg.text.strip() for seg in segments if seg.text and seg.text.strip()]
    return " ".join(parts).strip()


def _load_qwen_asr(spec: ModelSpec) -> Any:
    import torch
    from qwen_asr import Qwen3ASRModel

    hf_id = spec.hf_id or ""
    return Qwen3ASRModel.from_pretrained(
        hf_id,
        device_map="cpu",
        dtype=torch.float32,
        max_new_tokens=448,
        max_inference_batch_size=1,
    )


def _transcribe_qwen_asr(model: Any, audio_path: str) -> str:
    results = model.transcribe(
        audio=audio_path,
        language=["Uzbek"],
        return_time_stamps=False,
    )
    return (results[0].text or "").strip()


def _load_mms(spec: ModelSpec) -> tuple[Any, Any]:
    import torch
    from transformers import AutoProcessor, Wav2Vec2ForCTC

    hf_id = spec.hf_id or ""
    processor = AutoProcessor.from_pretrained(hf_id)
    model = Wav2Vec2ForCTC.from_pretrained(hf_id)
    processor.tokenizer.set_target_lang(MMS_UZ_TARGET_LANG)
    model.load_adapter(MMS_UZ_TARGET_LANG)
    model.eval()
    return processor, model


def _transcribe_mms(bundle: tuple[Any, Any], audio_path: str) -> str:
    import torch

    processor, model = bundle
    samples = load_mono_resampled(audio_path)
    parts: list[str] = []
    for chunk in iter_chunks(samples):
        inputs = processor(chunk, sampling_rate=16_000, return_tensors="pt")
        with torch.no_grad():
            logits = model(inputs.input_values).logits
        ids = torch.argmax(logits, dim=-1)
        text = processor.batch_decode(ids)[0]
        if text and text.strip():
            parts.append(text.strip())
    return " ".join(parts).strip()
