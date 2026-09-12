"""
Prepare OSSDD (OpenSARShip) WebDataset shards for Ultralytics YOLO26.

Designed for Colab/cloud training: downloads one Hugging Face TAR shard at a
time, converts Sentinel-1 VV GeoTIFF chips to 8-bit grayscale PNGs, converts
OSSDD axis-aligned boxes to YOLO labels, then deletes the TAR before moving on.
This avoids keeping the full 72+ GB OSSDD archive on disk.

Default output:
    ossdd_yolo/
      images/train, labels/train
      images/val,   labels/val
      data.yaml

Usage:
    python training/prepare_ossdd_yolo.py
    python training/prepare_ossdd_yolo.py --max-train 500  # smoke test
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
from pathlib import Path

import numpy as np
import rasterio
import webdataset as wds
from PIL import Image
from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "sylviaHoch/OpenSARShip-Ship-Detection-Dataset"
OUT_DIR = Path("ossdd_yolo")


def decode_boxes(raw: bytes) -> list[list[float]]:
    boxes: list[list[float]] = []
    lines = raw.decode("utf-8").strip().splitlines()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 5:
            boxes.append([
                float(parts[1]),
                float(parts[2]),
                float(parts[3]),
                float(parts[4]),
            ])
    return boxes


def normalize_vv(raw_tif: bytes) -> np.ndarray:
    with rasterio.open(io.BytesIO(raw_tif)) as src:
        vv = src.read(1).astype(np.float32)

    finite = vv[np.isfinite(vv)]
    if finite.size == 0:
        raise ValueError("VV chip contains no finite pixels")

    positive = finite[finite > 0]
    values = positive if positive.size else finite
    lo, hi = np.percentile(values, [2, 98])
    if hi <= lo:
        hi = lo + 1.0

    image = np.clip((vv - lo) / (hi - lo), 0.0, 1.0)
    return (image * 255.0).astype(np.uint8)


def save_sample(item: dict, split: str, index: int) -> bool:
    if "vv.tif" not in item or "aabb.txt" not in item:
        return False

    boxes = decode_boxes(item["aabb.txt"])
    image = normalize_vv(item["vv.tif"])
    h, w = image.shape

    key = str(item.get("__key__", f"sample_{index:08d}"))
    safe_key = key.replace("/", "_").replace("\\", "_")

    image_path = OUT_DIR / "images" / split / f"{safe_key}.png"
    label_path = OUT_DIR / "labels" / split / f"{safe_key}.txt"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)

    Image.fromarray(image, mode="L").save(image_path, optimize=True)

    lines = []
    for xmin, ymin, xmax, ymax in boxes:
        xmin = max(0.0, min(float(xmin), w))
        xmax = max(0.0, min(float(xmax), w))
        ymin = max(0.0, min(float(ymin), h))
        ymax = max(0.0, min(float(ymax), h))
        if xmax <= xmin or ymax <= ymin:
            continue
        cx = ((xmin + xmax) / 2.0) / w
        cy = ((ymin + ymax) / 2.0) / h
        bw = (xmax - xmin) / w
        bh = (ymax - ymin) / h
        lines.append(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

    label_path.write_text("\n".join(lines), encoding="utf-8")
    return True


def shard_files(split: str) -> list[str]:
    api = HfApi()
    files = api.list_repo_files(repo_id=REPO_ID, repo_type="dataset")
    prefix = f"webdataset/{split}/"
    return sorted(
        f for f in files
        if f.startswith(prefix) and f.endswith(".tar")
    )


def process_split(split: str, max_samples: int | None) -> int:
    shards = shard_files(split)
    if not shards:
        raise RuntimeError(f"No WebDataset shards found for split={split}")

    print(f"{split}: {len(shards)} shards")
    total = 0

    for shard_no, filename in enumerate(shards, start=1):
        if max_samples is not None and total >= max_samples:
            break

        local = Path(hf_hub_download(
            repo_id=REPO_ID,
            filename=filename,
            repo_type="dataset",
        ))

        print(f"[{split} {shard_no}/{len(shards)}] {filename}")
        dataset = wds.WebDataset(str(local), shardshuffle=False)

        for item in dataset:
            if max_samples is not None and total >= max_samples:
                break
            if save_sample(item, split, total):
                total += 1

        try:
            local.unlink()
        except OSError:
            pass

    return total


def write_yaml() -> None:
    yaml_text = (
        f"path: {OUT_DIR.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "nc: 1\n"
        "names: [ship]\n"
    )
    (OUT_DIR / "data.yaml").write_text(yaml_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-train", type=int, default=None)
    parser.add_argument("--max-val", type=int, default=None)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if args.clean and OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    train_n = process_split("train", args.max_train)
    val_n = process_split("val", args.max_val)
    write_yaml()

    print("\nOSSDD YOLO preparation complete")
    print(f"Train images: {train_n}")
    print(f"Val images:   {val_n}")
    print(f"Dataset YAML: {OUT_DIR / 'data.yaml'}")


if __name__ == "__main__":
    main()
