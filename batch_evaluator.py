"""Evaluate the complete SIH pipeline across every held-out SAR chip.

Run from the repository root:
    python batch_evaluator.py

By default the evaluator uses the pipeline's synthetic AIS test pings. Pass
``--real-ais`` to load the configured MarineCadastre data set instead.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import tempfile
import time

import numpy as np
from PIL import Image
import torch

from main.ais_matcher import (
    AIS_CSV_PATH,
    generate_synthetic_ais_for_hulls,
    load_ais_data,
)
from main.integration_pipeline import run_full_pipeline
from main import ocean_wind_loader
from main.predict_and_classify import load_model


TEST_IMAGES_PATH = Path("data/processed/test_images.npy")
SUSPECT_THRESHOLD = 0.90


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all four pipeline stages on every test SAR chip."
    )
    parser.add_argument(
        "--real-ais",
        action="store_true",
        help="Use the configured MarineCadastre AIS data instead of synthetic test pings.",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of chips to evaluate (default: 50).",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="Evaluate all held-out chips instead of the default 50-chip benchmark.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be a positive integer")
    return args


def load_ais_records(use_real_ais: bool):
    if use_real_ais:
        print(f"Loading real AIS records from {AIS_CSV_PATH}...")
        return load_ais_data(AIS_CSV_PATH)

    print("Using synthetic per-image AIS pings (about 15% of hulls are AIS-off)...")
    def synthetic_ais_for_detected_hulls(hulls, image_id: str):
        return generate_synthetic_ais_for_hulls(
            [
                {
                    "hull_id": hull.hull_id,
                    "lat": hull.lat,
                    "lon": hull.lon,
                    "timestamp": datetime.fromisoformat(
                        hull.timestamp.replace("Z", "+00:00")
                    ).replace(tzinfo=None),
                }
                for hull in hulls
            ],
            image_id,
        )

    return synthetic_ais_for_detected_hulls


def install_weather_cache():
    """Patch Stage 4's loader for this batch run and return cache statistics.

    The cache deliberately uses only rounded coordinates as its key: every chip
    in a batch represents the same evaluation pass, and the requirement is one
    Open-Meteo fetch at most per location.  Copies keep Stage 4's temporary
    DataFrame columns from modifying the cached response.
    """
    cache = {}
    weather_fetch_seconds = [0.0]
    original_fetch = ocean_wind_loader.fetch_currents_and_wind

    def cached_fetch(lat: float, lon: float, start_date: str, end_date: str):
        key = (round(float(lat), 6), round(float(lon), 6))
        if key not in cache:
            fetch_started_at = time.perf_counter()
            cache[key] = original_fetch(lat, lon, start_date, end_date)
            weather_fetch_seconds[0] += time.perf_counter() - fetch_started_at
        return cache[key].copy(deep=True)

    ocean_wind_loader.fetch_currents_and_wind = cached_fetch
    return original_fetch, cache, weather_fetch_seconds


def main() -> None:
    args = parse_args()
    test_images = np.load(TEST_IMAGES_PATH)
    selected_images = test_images if args.all else test_images[: args.limit]

    print("Loading slick detection model...")
    slick_model = load_model()
    slick_model.eval()
    ais_df = load_ais_records(args.real_ais)

    total_linear = 0
    total_blob = 0
    total_suspects = 0
    latencies_ms: list[float] = []

    original_weather_fetch, weather_cache, weather_fetch_seconds = install_weather_cache()

    print(f"Evaluating {len(selected_images)} SAR chips...\n")
    # The hull detector requires a file path, so each in-memory chip is made
    # available as a temporary JPEG. Image conversion is intentionally outside
    # the timer; latency measures the four pipeline stages themselves.
    try:
        with tempfile.TemporaryDirectory(prefix="sih_batch_") as temp_dir:
            temp_dir_path = Path(temp_dir)

            for index, image_rgb in enumerate(selected_images):
                image_id = f"test_{index}"
                image_path = temp_dir_path / f"{image_id}.jpg"
                Image.fromarray(image_rgb).save(image_path)

                weather_seconds_before = weather_fetch_seconds[0]
                started_at = time.perf_counter()
                try:
                    # Keep segmentation and every tensor it creates out of autograd.
                    with torch.inference_mode():
                        output = run_full_pipeline(
                            image_id=image_id,
                            image_rgb=image_rgb,
                            image_path=str(image_path),
                            slick_model=slick_model,
                            ais_df=ais_df,
                        )
                    finished_at = time.perf_counter()
                except Exception as e:
                    print(
                        f"[warning] {image_id}: pipeline request failed "
                        f"({type(e).__name__}: {e}); skipping image."
                    )
                    continue

                # A cache miss is setup/network time, not pipeline compute time.
                weather_seconds = weather_fetch_seconds[0] - weather_seconds_before
                latency_ms = max(0.0, (finished_at - started_at - weather_seconds) * 1_000)
                latencies_ms.append(latency_ms)

                total_linear += output.slicks.num_linear
                total_blob += output.slicks.num_blob
                total_suspects += sum(
                    1
                    for match in output.ais_matches.matches
                    if not match.has_ais_match
                    and match.suspicion_score >= SUSPECT_THRESHOLD
                )
                print(f"{image_id}: {latency_ms:.2f} ms pure pipeline")
    finally:
        # This process normally exits immediately, but restore the module for
        # callers that invoke main() from an interactive session or test.
        ocean_wind_loader.fetch_currents_and_wind = original_weather_fetch

    average_latency_ms = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
    projected_throughput = 1_000 / average_latency_ms if average_latency_ms else 0.0
    label_width = 39
    print("\nBatch Evaluation Summary")
    print("-" * (label_width + 18))
    print(f"{'SAR Chips Processed':<{label_width}} {len(latencies_ms):>12}")
    print(f"{'Pure Pipeline Processing Latency (ms/chip)':<{label_width}} {average_latency_ms:>12.2f}")
    print(f"{'Projected Full-Swath Throughput (chips/sec)':<{label_width}} {projected_throughput:>12.2f}")
    print(f"{'Linear Slicks vs. Blobs':<{label_width}} {total_linear} linear / {total_blob} blob")
    print(
        f"{'Flagged Dark Vessel Suspects':<{label_width}} "
        f"{total_suspects:>12} (score >= {SUSPECT_THRESHOLD:.2f})"
    )
    print(f"{'Unique weather locations fetched':<{label_width}} {len(weather_cache):>12}")


if __name__ == "__main__":
    main()
