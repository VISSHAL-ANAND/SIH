"""Temporary visual validator for SAR ship detections.

Run against a large Sentinel-1 VV TIFF. It reuses the real detector, creates a
small downsampled preview, draws the detector boxes, and writes a JSON sidecar.
This file is intentionally temporary and can be deleted after validation.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from main.ship_detection_module import detect_hulls


def _normalize_for_preview(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float32)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = np.percentile(arr, [2.0, 98.0])
    if hi <= lo:
        lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    return np.clip((arr - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


def create_preview(image_path: str, output_path: str, max_side: int = 1800) -> list:
    import rasterio

    detections = detect_hulls(image_path)
    with rasterio.open(image_path) as src:
        scale = min(1.0, max_side / max(src.width, src.height))
        out_w = max(1, int(round(src.width * scale)))
        out_h = max(1, int(round(src.height * scale)))
        preview = src.read(
            1,
            out_shape=(out_h, out_w),
            resampling=rasterio.enums.Resampling.average,
        )

    rgb = np.stack([_normalize_for_preview(preview)] * 3, axis=-1)
    image = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    for index, det in enumerate(detections, start=1):
        x1, y1, x2, y2 = det["bbox_px"]
        sx = image.width / max(1, preview.shape[1])
        sy = image.height / max(1, preview.shape[0])
        box = (x1 * sx, y1 * sy, x2 * sx, y2 * sy)
        draw.rectangle(box, outline=(255, 0, 0), width=2)
        label = f"#{index} {det['confidence']:.2f}"
        tx, ty = box[0] + 2, max(0, box[1] - 12)
        draw.text((tx, ty), label, fill=(255, 255, 0), font=font)

    image.save(output_path, quality=92)
    sidecar = str(Path(output_path).with_suffix(".json"))
    Path(sidecar).write_text(json.dumps(detections, indent=2), encoding="utf-8")
    return detections


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a small visual validator for SAR ship detections")
    parser.add_argument("image")
    parser.add_argument("--output", default="ship_detection_validation.jpg")
    parser.add_argument("--max-side", type=int, default=1800)
    args = parser.parse_args()
    detections = create_preview(args.image, args.output, args.max_side)
    print(f"DETECTIONS: {len(detections)}")
    print(f"PREVIEW: {Path(args.output).resolve()}")
    print(f"JSON: {Path(args.output).with_suffix('.json').resolve()}")


if __name__ == "__main__":
    main()
