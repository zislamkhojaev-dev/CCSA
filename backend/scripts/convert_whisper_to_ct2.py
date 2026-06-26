#!/usr/bin/env python3
"""CLI: convert HF Whisper to faster-whisper INT8 (see stt/model_convert.py)."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stt.model_convert import DEFAULT_UZ_HF_ID, convert_hf_whisper_to_ct2, ct2_output_dir


def main() -> None:
    p = argparse.ArgumentParser(description="Convert HF Whisper to faster-whisper INT8")
    p.add_argument("--model", default=DEFAULT_UZ_HF_ID, help="Hugging Face model id")
    p.add_argument("--output", default=None, help="Output directory")
    p.add_argument("--quantization", default="int8", choices=("int8", "float16", "float32"))
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    out = args.output or ct2_output_dir(args.model)
    path = convert_hf_whisper_to_ct2(
        args.model,
        out,
        quantization=args.quantization,
        force=args.force,
    )
    print(f"Saved CT2 model to: {path}")


if __name__ == "__main__":
    main()
