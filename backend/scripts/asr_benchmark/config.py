from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scripts.asr_benchmark.hf_hub import MMS_1B_ALL_HF_ID, QWEN3_ASR_UZ_HF_ID
from scripts.asr_benchmark.transformers_int8 import is_ready as transformers_int8_ready

Engine = Literal["transformers", "ct2", "qwen_asr", "mms"]

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_DIR = ROOT / "benchmark"
AUDIO_DIR = BENCHMARK_DIR / "audio"
RESULTS_DIR = BENCHMARK_DIR / "results"
MODELS_DIR = ROOT / "models"

DEFAULT_UZ_HF_ID = "OvozifyLabs/whisper-small-uz-v1"
ZEHNOVA_HF_ID = "Jonibek21/Zehnova-Uzbek-STT"
CT2_INT8_DIR = MODELS_DIR / "OvozifyLabs--whisper-small-uz-v1-int8"
CT2_FP32_DIR = MODELS_DIR / "OvozifyLabs--whisper-small-uz-v1-fp32"
TRANSFORMERS_INT8_DIR = MODELS_DIR / "OvozifyLabs--whisper-small-uz-v1-transformers-int8"

AUDIO_EXTENSIONS = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm")
BASELINE_SLUG = "ovozify-transformers-fp32"
MMS_UZ_TARGET_LANG = "uzb-script_latin"
WAVE2_SLUGS = frozenset({"qwen3-asr-uzbek-v2", "mms-1b-all-uz"})


@dataclass(frozen=True)
class ModelSpec:
    slug: str
    label: str
    engine: Engine
    hf_id: str | None = None
    transformers_path: str | None = None
    ct2_path: str | None = None
    compute_type: str | None = None
    is_baseline: bool = False


def wave1_model_specs() -> list[ModelSpec]:
    return [
        ModelSpec(
            slug="ovozify-transformers-fp32",
            label="OvozifyLabs/whisper-small-uz-v1 (transformers, fp32)",
            engine="transformers",
            hf_id=DEFAULT_UZ_HF_ID,
            is_baseline=True,
        ),
        ModelSpec(
            slug="zehnova-transformers",
            label="Jonibek21/Zehnova-Uzbek-STT (transformers)",
            engine="transformers",
            hf_id=ZEHNOVA_HF_ID,
        ),
        ModelSpec(
            slug="ovozify-transformers-int8",
            label="OvozifyLabs/whisper-small-uz-v1 (transformers, int8)",
            engine="transformers",
            transformers_path=str(TRANSFORMERS_INT8_DIR),
        ),
        ModelSpec(
            slug="ovozify-ct2-fp32",
            label="OvozifyLabs/whisper-small-uz-v1 (CT2, float32)",
            engine="ct2",
            ct2_path=str(CT2_FP32_DIR),
            compute_type="float32",
        ),
        ModelSpec(
            slug="ovozify-ct2-int8",
            label="OvozifyLabs/whisper-small-uz-v1 (CT2, int8)",
            engine="ct2",
            ct2_path=str(CT2_INT8_DIR),
            compute_type="int8",
        ),
    ]


def wave2_model_specs(*, include_qwen: bool = False) -> list[ModelSpec]:
    specs: list[ModelSpec] = [
        ModelSpec(
            slug="mms-1b-all-uz",
            label="facebook/mms-1b-all (MMS CTC, uzb-script_latin)",
            engine="mms",
            hf_id=MMS_1B_ALL_HF_ID,
        ),
    ]
    if include_qwen:
        specs.insert(
            0,
            ModelSpec(
                slug="qwen3-asr-uzbek-v2",
                label="Gearnode/qwen3-asr-uzbek-v2 (qwen_asr, CPU fp32)",
                engine="qwen_asr",
                hf_id=QWEN3_ASR_UZ_HF_ID,
            ),
        )
    return specs


def model_specs(*, wave2_only: bool = False, include_qwen: bool = False) -> list[ModelSpec]:
    if wave2_only:
        return wave2_model_specs(include_qwen=include_qwen)
    return wave1_model_specs() + wave2_model_specs(include_qwen=include_qwen)


def discover_audio_files(audio_dir: Path | None = None) -> list[Path]:
    base = audio_dir or AUDIO_DIR
    if not base.is_dir():
        return []
    found: dict[int, Path] = {}
    for path in sorted(base.iterdir()):
        if not path.is_file():
            continue
        stem = path.stem
        if not stem.isdigit():
            continue
        idx = int(stem)
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        found[idx] = path
    return [found[k] for k in sorted(found)]


def output_run_dir(run_id: str | None = None) -> Path:
    if run_id:
        return RESULTS_DIR / run_id
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return RESULTS_DIR / ts


def ct2_ready(path: Path) -> bool:
    return (path / "model.bin").is_file()


def missing_artifacts(*, wave1_only: bool = True) -> list[str]:
    """Return human-readable paths of benchmark artifacts that are not ready."""
    if not wave1_only:
        return []
    missing: list[str] = []
    if not ct2_ready(CT2_INT8_DIR):
        missing.append(f"CT2 int8: {CT2_INT8_DIR}")
    if not ct2_ready(CT2_FP32_DIR):
        missing.append(f"CT2 fp32: {CT2_FP32_DIR}")
    if not transformers_int8_ready(TRANSFORMERS_INT8_DIR):
        missing.append(f"Transformers int8: {TRANSFORMERS_INT8_DIR}")
    return missing
