#!/usr/bin/env python3
"""Prepare all local model artifacts for the ASR benchmark."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.asr_benchmark.hf_hub import configure_hf_hub  # noqa: E402

configure_hf_hub()

from scripts.asr_benchmark.config import (  # noqa: E402
    CT2_FP32_DIR,
    CT2_INT8_DIR,
    DEFAULT_UZ_HF_ID,
    TRANSFORMERS_INT8_DIR,
    ct2_ready,
    missing_artifacts,
)
from scripts.asr_benchmark.transformers_int8 import (  # noqa: E402
    is_ready as transformers_int8_ready,
    load_transformers_int8_pipeline,
    prepare_transformers_int8,
)
from stt.model_convert import convert_hf_whisper_to_ct2  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _prepare_ct2(hf_id: str, output: Path, quantization: str, *, force: bool) -> None:
    if ct2_ready(output) and not force:
        print(f"OK  {output} ({quantization})")
        return
    print(f"Converting {hf_id} -> {output} ({quantization}) ...")
    path = convert_hf_whisper_to_ct2(
        hf_id,
        str(output),
        quantization=quantization,
        force=force,
    )
    print(f"Saved {path}")


def _prepare_transformers_int8(hf_id: str, output: Path, *, force: bool) -> None:
    if transformers_int8_ready(output) and not force:
        print(f"OK  {output} (transformers int8)")
        return
    print(f"Preparing transformers int8 {hf_id} -> {output} ...")
    path = prepare_transformers_int8(hf_id, output, force=force)
    print(f"Saved {path}")


def _make_smoke_wav(path: Path, duration_ms: int = 500) -> None:
    from pydub import AudioSegment
    from pydub.generators import Sine

    tone = Sine(440).to_audio_segment(duration=duration_ms).set_channels(1)
    tone.export(path, format="wav")


def _smoke_test() -> None:
    """Load each prepared artifact and run a short transcription."""
    from faster_whisper import WhisperModel

    from scripts.asr_benchmark.config import DEFAULT_UZ_HF_ID, ModelSpec  # noqa: E402
    from scripts.asr_benchmark.transcribers import (  # noqa: E402
        _load_transformers,
        _transcribe_ct2,
        _transcribe_transformers,
    )

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "smoke.wav"
        _make_smoke_wav(wav)

        print("\nSmoke test: transformers int8 ...")
        pipe = load_transformers_int8_pipeline(TRANSFORMERS_INT8_DIR)
        text = _transcribe_transformers(pipe, str(wav))
        print(f"  OK  text={text!r}")

        print("Smoke test: transformers fp32 (Hub) ...")
        fp32_spec = ModelSpec(
            slug="smoke-fp32",
            label="smoke",
            engine="transformers",
            hf_id=DEFAULT_UZ_HF_ID,
        )
        pipe = _load_transformers(fp32_spec)
        text = _transcribe_transformers(pipe, str(wav))
        print(f"  OK  text={text!r}")

        for label, model_path, compute_type in (
            ("CT2 int8", CT2_INT8_DIR, "int8"),
            ("CT2 fp32", CT2_FP32_DIR, "float32"),
        ):
            print(f"Smoke test: {label} ...")
            model = WhisperModel(str(model_path), device="cpu", compute_type=compute_type)
            text = _transcribe_ct2(model, str(wav))
            print(f"  OK  text={text!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare ASR benchmark model artifacts")
    parser.add_argument("--force", action="store_true", help="Rebuild existing artifacts")
    parser.add_argument(
        "--only",
        choices=("all", "ct2", "transformers-int8"),
        default="all",
        help="Which artifacts to prepare",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="After preparation, load each artifact and transcribe a short clip",
    )
    args = parser.parse_args()

    if args.only in ("all", "ct2"):
        _prepare_ct2(DEFAULT_UZ_HF_ID, CT2_INT8_DIR, "int8", force=args.force)
        _prepare_ct2(DEFAULT_UZ_HF_ID, CT2_FP32_DIR, "float32", force=args.force)

    if args.only in ("all", "transformers-int8"):
        _prepare_transformers_int8(DEFAULT_UZ_HF_ID, TRANSFORMERS_INT8_DIR, force=args.force)

    still_missing = missing_artifacts()
    if still_missing:
        if args.only == "all":
            raise SystemExit("Artifacts still missing:\n  " + "\n  ".join(still_missing))
        print("\nOther artifacts still missing:")
        for item in still_missing:
            print(f"  - {item}")
    else:
        print("\nAll benchmark artifacts ready.")
    print("HF models for fp32/Zehnova download on first benchmark run.")

    if args.smoke:
        _smoke_test()


if __name__ == "__main__":
    main()
