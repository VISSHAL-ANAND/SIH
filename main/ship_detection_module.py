"""
SIH26143 — Ship-detection pipeline module.

The trained YOLO checkpoint is configurable through IMW_HULL_CHECKPOINT so
model binaries remain outside Git while deployment paths stay explicit.
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "runs" / "detect" / "sar_hull_detector" / "weights" / "best_unet.pt"
WEIGHTS_PATH = os.getenv("IMW_HULL_CHECKPOINT", str(DEFAULT_WEIGHTS_PATH))
CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45

_model = None


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO
        weights = Path(WEIGHTS_PATH)
        if not weights.exists():
            raise FileNotFoundError(
                f"Trained SAR hull weights not found: {weights}. "
                "Set IMW_HULL_CHECKPOINT or provide the expected checkpoint. "
                "IMW will not substitute a generic pretrained detector."
            )
        _model = YOLO(str(weights))
    return _model


def _try_read_geotransform(image_path: str):
    try:
        import rasterio
    except ImportError:
        return None, None
    try:
        with rasterio.open(image_path) as src:
            if src.transform is not None and not src.transform.is_identity:
                return src.transform, src.crs
    except Exception:
        pass
    return None, None


def _pixel_to_latlon(transform, crs, px, py):
    import rasterio
    from pyproj import Transformer
    lon, lat = rasterio.transform.xy(transform, py, px)
    if crs is not None and crs.to_epsg() != 4326:
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(lon, lat)
    return lat, lon


def _try_extract_timestamp(image_path: str):
    """Extract Sentinel-1 acquisition time from the filename or file mtime."""
    name = Path(image_path).stem
    m = re.search(r"(\d{8}T\d{6})", name)
    if m:
        dt = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    try:
        dt = datetime.fromtimestamp(Path(image_path).stat().st_mtime, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def detect_hulls(image_path: str, conf: float = CONF_THRESHOLD, iou: float = IOU_THRESHOLD,
                 timestamp: str = None) -> list:
    model = _get_model()
    results = model.predict(image_path, imgsz=800, conf=conf, iou=iou, verbose=False)
    transform, crs = _try_read_geotransform(image_path)
    ts = timestamp or _try_extract_timestamp(image_path)

    detections = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            confidence = box.conf.item()
            lat = lon = None
            if transform is not None:
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                lat, lon = _pixel_to_latlon(transform, crs, cx, cy)
            detections.append({
                "bbox_px": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                "confidence": round(confidence, 3),
                "lat": round(lat, 6) if lat is not None else None,
                "lon": round(lon, 6) if lon is not None else None,
                "timestamp": ts,
            })
    return detections


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("image", help="Path to a SAR image or georeferenced scene")
    p.add_argument("--conf", type=float, default=CONF_THRESHOLD)
    p.add_argument("--iou", type=float, default=IOU_THRESHOLD)
    p.add_argument("--timestamp", type=str, default=None)
    p.add_argument("--json", type=str, default=None)
    args = p.parse_args()

    dets = detect_hulls(args.image, conf=args.conf, iou=args.iou, timestamp=args.timestamp)
    print(f"\n{args.image}: {len(dets)} hull(s) detected")
    for d in dets:
        geo = f"lat={d['lat']}, lon={d['lon']}" if d["lat"] is not None else "no geo metadata"
        print(f"  bbox={d['bbox_px']}  conf={d['confidence']}  {geo}  ts={d['timestamp']}")
    if args.json:
        Path(args.json).write_text(json.dumps(dets, indent=2))
        print(f"\nWrote {args.json}")
