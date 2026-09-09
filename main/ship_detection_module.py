"""
SIH26143 — Ship-detection pipeline module
=============================================

Callable interface: SAR image in -> list of hull detections out.
This is what ASHMIL's AIS matcher and RATHIMEE's full-pipeline wiring
import directly.

Handles two input cases:
  1. Georeferenced SAR product (GeoTIFF with an affine transform) ->
     returns real lat/lon for each detected hull.
  2. Plain image (jpg/png chip, no geo metadata) -> returns pixel
     coordinates only, with geo fields set to None. Still works for
     demo chips that aren't full georeferenced scenes.

Usage as a library
-------------------
    from main.ship_detection_module import detect_hulls

    detections = detect_hulls("scene.tif")
    # -> [
    #      {
    #        "bbox_px": [x1, y1, x2, y2],
    #        "confidence": 0.91,
    #        "lat": 10.234, "lon": 78.912,   # None if no geo metadata
    #        "timestamp": "2026-08-20T03:14:00Z",  # None if not derivable
    #      },
    #      ...
    #    ]

Usage from the command line
-----------------------------
    python -m main.ship_detection_module path/to/scene.tif
    python -m main.ship_detection_module path/to/scene.tif --json out.json
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

WEIGHTS_PATH = str(Path(__file__).resolve().parent.parent / "runs" / "detect" / "sar_hull_detector" / "weights" / "best_unet.pt")
CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45

_model = None  # lazy-loaded singleton so repeated calls don't reload weights


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO
        weights = WEIGHTS_PATH
        if not Path(weights).exists():
            raise FileNotFoundError(
                f"Trained SAR hull weights not found: {weights}. "
                "IMW will not substitute a generic pretrained detector."
            )
        _model = YOLO(weights)
    return _model



def _try_read_geotransform(image_path: str):
    """
    Returns (transform, crs) if the image is a georeferenced raster
    (e.g. GeoTIFF), else (None, None). Requires rasterio, which is
    optional — plain jpg/png chips just skip this and return pixel-only
    results.
    """
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
    """Convert a pixel (col, row) to lat/lon (WGS84), given a rasterio transform+crs."""
    import rasterio
    from pyproj import Transformer

    lon, lat = rasterio.transform.xy(transform, py, px)
    if crs is not None and crs.to_epsg() != 4326:
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(lon, lat)
    return lat, lon


def _try_extract_timestamp(image_path: str):
    """
    Sentinel-1 product filenames encode acquisition time, e.g.:
    S1A_IW_GRDH_1SDV_20260820T031400_20260820T031425_...
    Falls back to file modification time if the filename doesn't match,
    and to None if that also fails. Downstream code (AIS matcher) should
    treat None as "ask the user / use scene metadata instead."
    """
    name = Path(image_path).stem
    m = re.search(r"(\d{8}T\d{6})", name)
    if m:
        dt = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")

    try:
        mtime = Path(image_path).stat().st_mtime
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def detect_hulls(image_path: str, conf: float = CONF_THRESHOLD, iou: float = IOU_THRESHOLD,
                  timestamp: str = None) -> list:
    """
    Run hull detection on a single SAR image/scene.

    Parameters
    ----------
    image_path : path to the image (jpg/png chip, or georeferenced GeoTIFF scene)
    conf, iou  : detection thresholds (defaults tuned during training)
    timestamp  : override for acquisition time (ISO 8601). If not given,
                 attempts to parse it from a Sentinel-1-style filename,
                 then falls back to file mtime.

    Returns
    -------
    List of dicts: bbox_px, confidence, lat, lon, timestamp
    (lat/lon are None if the image has no geo metadata)
    """
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
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2  # box center, pixel coords
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
    p.add_argument("--timestamp", type=str, default=None, help="Override ISO 8601 timestamp")
    p.add_argument("--json", type=str, default=None, help="Optional path to write results as JSON")
    args = p.parse_args()

    dets = detect_hulls(args.image, conf=args.conf, iou=args.iou, timestamp=args.timestamp)

    print(f"\n{args.image}: {len(dets)} hull(s) detected")
    for d in dets:
        geo = f"lat={d['lat']}, lon={d['lon']}" if d["lat"] is not None else "no geo metadata"
        print(f"  bbox={d['bbox_px']}  conf={d['confidence']}  {geo}  ts={d['timestamp']}")

    if args.json:
        Path(args.json).write_text(json.dumps(dets, indent=2))
        print(f"\nWrote {args.json}")
