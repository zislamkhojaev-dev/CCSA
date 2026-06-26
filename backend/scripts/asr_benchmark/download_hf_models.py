#!/usr/bin/env python3
"""Prefetch Hugging Face models for the ASR benchmark (fast transfer enabled)."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.asr_benchmark.config import DEFAULT_UZ_HF_ID  # noqa: E402
from scripts.asr_benchmark.hf_hub import (  # noqa: E402
    BENCHMARK_HF_MODEL_IDS,
    WAVE2_HF_MODEL_IDS,
    WAVE2_MMS_ONLY_HF_MODEL_IDS,
    ZEHNOVA_HF_ID,
    configure_hf_hub,
    ensure_hf_transfer,
    hf_download_kwargs,
    hf_token_status,
)


def _cache_dir_for_repo(cache_root: Path, repo_id: str) -> Path:
    return cache_root / ("models--" + repo_id.replace("/", "--"))


def _dir_size_mb(path: Path) -> float:
    if not path.is_dir():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def _incomplete_stats(target: Path) -> tuple[int, float]:
    if not target.is_dir():
        return 0, 0.0
    files = list(target.rglob("*.incomplete"))
    partial_mb = sum(f.stat().st_size for f in files if f.is_file()) / (1024 * 1024)
    return len(files), partial_mb


def _print_download_tick(
    *,
    repo_id: str,
    cache_mb: float,
    delta_mb: float,
    elapsed_sec: float,
    incomplete_n: int,
    partial_mb: float,
    stalled_ticks: int,
) -> None:
    mins, secs = divmod(int(elapsed_sec), 60)
    delta_s = f"+{delta_mb:.1f} MB" if delta_mb > 0.01 else "no change"
    stall_s = f", stalled x{stalled_ticks}" if stalled_ticks >= 2 else ""
    inc_s = (
        f", {incomplete_n} partial file(s) ({partial_mb:.1f} MB)"
        if incomplete_n
        else ""
    )
    line = (
        f"  [{mins:02d}:{secs:02d}] {repo_id}: {cache_mb:.1f} MB ({delta_s}{inc_s}{stall_s})\n"
    )
    sys.stderr.write(line)
    sys.stderr.flush()


def _watch_download(
    cache_root: Path,
    repo_id: str,
    stop: threading.Event,
    *,
    interval_sec: float,
) -> None:
    target = _cache_dir_for_repo(cache_root, repo_id)
    last_mb = _dir_size_mb(target)
    stalled_ticks = 0
    started = time.monotonic()
    incomplete_n, partial_mb = _incomplete_stats(target)
    _print_download_tick(
        repo_id=repo_id,
        cache_mb=last_mb,
        delta_mb=0.0,
        elapsed_sec=0.0,
        incomplete_n=incomplete_n,
        partial_mb=partial_mb,
        stalled_ticks=0,
    )
    while True:
        if stop.wait(interval_sec):
            break
        mb = _dir_size_mb(target)
        elapsed = time.monotonic() - started
        delta = mb - last_mb
        incomplete_n, partial_mb = _incomplete_stats(target)
        if delta <= 0.01:
            stalled_ticks += 1
        else:
            stalled_ticks = 0
        _print_download_tick(
            repo_id=repo_id,
            cache_mb=mb,
            delta_mb=delta,
            elapsed_sec=elapsed,
            incomplete_n=incomplete_n,
            partial_mb=partial_mb,
            stalled_ticks=stalled_ticks,
        )
        last_mb = mb
        if stalled_ticks >= 8:
            sys.stderr.write(
                "  [!] No growth for 2+ min — try: HF_HUB_ENABLE_HF_TRANSFER=0 "
                "make benchmark-download-wave2\n"
            )
            sys.stderr.flush()
            stalled_ticks = 0


def _download(
    repo_id: str,
    *,
    cache_root: Path,
    use_hf_transfer: bool,
    watch_interval_sec: float,
) -> None:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import GatedRepoError, HfHubHTTPError

    print(f"\n=== Download {repo_id} ===")
    if use_hf_transfer:
        print(
            "  hf_transfer enabled. If size stalls >2 min, retry with:\n"
            "  HF_HUB_ENABLE_HF_TRANSFER=0 make benchmark-download-wave2",
            flush=True,
        )
    print(
        f"  Status every {watch_interval_sec:.0f}s on stderr "
        f"(cache: {_cache_dir_for_repo(cache_root, repo_id)})",
        flush=True,
    )
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_download,
        args=(cache_root, repo_id, stop),
        kwargs={"interval_sec": watch_interval_sec},
        daemon=True,
    )
    watcher.start()
    kwargs = hf_download_kwargs()
    kwargs["cache_dir"] = str(cache_root)
    try:
        path = snapshot_download(repo_id, **kwargs)
    except GatedRepoError as e:
        raise SystemExit(
            f"Model {repo_id} is gated. Log in on huggingface.co, accept the license, "
            f"then set HF_TOKEN in .env (see benchmark/hf.env.example).\n{e}"
        ) from e
    except HfHubHTTPError as e:
        if getattr(e, "response", None) and e.response.status_code in (401, 403):
            raise SystemExit(
                "Hugging Face auth failed (401/403). Check HF_TOKEN in .env:\n"
                "  HF_TOKEN=hf_xxxxxxxx  (one line, with prefix hf_)\n"
                "Revoke the token if it was exposed and create a new one."
            ) from e
        raise
    finally:
        stop.set()
        watcher.join(timeout=1.0)
    mb = _dir_size_mb(Path(path))
    print(f"OK  {path} ({mb:.0f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prefetch HF models for ASR benchmark")
    parser.add_argument(
        "--zehnova-only",
        action="store_true",
        help=f"Only {ZEHNOVA_HF_ID} (~3 GB)",
    )
    parser.add_argument(
        "--ovozify-only",
        action="store_true",
        help=f"Only {DEFAULT_UZ_HF_ID}",
    )
    parser.add_argument(
        "--wave2-only",
        action="store_true",
        help="Wave-2 without Qwen: mms-1b-all only (see benchmark/MODELS.md)",
    )
    parser.add_argument(
        "--include-qwen",
        action="store_true",
        help="With --wave2-only: also download Gearnode/qwen3-asr-uzbek-v2 (~4 GB)",
    )
    parser.add_argument(
        "--no-hf-transfer",
        action="store_true",
        help="Disable hf_transfer (slower but more reliable on flaky networks)",
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=15.0,
        metavar="SEC",
        help="Print cache size to stderr every SEC seconds (default: 15)",
    )
    args = parser.parse_args()

    try:
        cache = configure_hf_hub()
    except ValueError as e:
        raise SystemExit(str(e)) from e
    print(f"HF cache: {cache}")
    print(f"HF token: {hf_token_status()}")
    use_hf_transfer = (
        not args.no_hf_transfer
        and os.environ.get("HF_HUB_ENABLE_HF_TRANSFER", "1") not in ("0", "false", "False")
        and ensure_hf_transfer()
    )
    if args.no_hf_transfer:
        os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
        print("hf_transfer: disabled (--no-hf-transfer)")
    elif use_hf_transfer:
        print("hf_transfer: enabled (HF_HUB_ENABLE_HF_TRANSFER=1)")
    else:
        print(
            "hf_transfer: not installed — pip install hf-transfer for faster downloads"
        )

    if args.zehnova_only:
        ids = [ZEHNOVA_HF_ID]
    elif args.ovozify_only:
        ids = [DEFAULT_UZ_HF_ID]
    elif args.wave2_only:
        ids = (
            list(WAVE2_HF_MODEL_IDS)
            if args.include_qwen
            else list(WAVE2_MMS_ONLY_HF_MODEL_IDS)
        )
        if not args.include_qwen:
            print("Skipping Qwen3-ASR (use --include-qwen to download ~4 GB)")
    else:
        ids = list(BENCHMARK_HF_MODEL_IDS)

    for repo_id in ids:
        _download(
            repo_id,
            cache_root=cache,
            use_hf_transfer=use_hf_transfer,
            watch_interval_sec=max(5.0, args.watch_interval),
        )

    print("\nAll requested models are in cache.")


if __name__ == "__main__":
    main()
