"""
SIH26143 — SAR ship-detection pipeline module.

Uses the trained YOLO SAR ship checkpoint and performs tiled inference on
large Sentinel-1 single-band measurement TIFFs. Each VV tile is normalized
and replicated to three channels for the YOLOv8 model. Detection boxes are
mapped back to full-scene pixel coordinates and, when possible, converted to
real WGS84 coordinates using GeoTIFF metadata or Sentinel-1 SAFE annotation
geolocation grids.
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
TILE_SIZE = 4096
TILE_OVERLAP = 0.15

_DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "runs" / "detect" / "sar_hull_detector" / "weights" / "best.pt"
_FALLBACK_MODEL = Path(__file__).resolve().parent.parent / "best_reconstructed.pt"
WEIGHTS_PATH = os.getenv("IMW_HULL_CHECKPOINT", str(_DEFAULT_MODEL))
_model = None


def _resolve_weights_path() -> Path:
    configured = Path(WEIGHTS_PATH)
    if configured.exists(): return configured
    if configured == _DEFAULT_MODEL and _FALLBACK_MODEL.exists(): return _FALLBACK_MODEL
    raise FileNotFoundError(f"Trained SAR ship weights not found: {configured}. Set IMW_HULL_CHECKPOINT or place the verified checkpoint at {_DEFAULT_MODEL}. IMW will not substitute a generic pretrained detector.")


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO
        weights = _resolve_weights_path()
        _model = YOLO(str(weights))
        names = getattr(_model, "names", {})
        if not names or "ship" not in {str(v).lower() for v in names.values()}:
            raise ValueError(f"Checkpoint {weights} is not the verified SAR ship detector. Model classes: {names}")
    return _model


def _try_read_geotransform(image_path: str):
    try:
        import rasterio
        with rasterio.open(image_path) as src:
            if src.transform is not None and not src.transform.is_identity:
                return src.transform, src.crs
    except Exception:
        pass
    return None, None


def _pixel_to_latlon(transform, crs, px, py):
    import rasterio
    from pyproj import Transformer
    x, y = rasterio.transform.xy(transform, py, px, offset="center")
    if crs is not None and crs.to_epsg() != 4326:
        x, y = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    return float(y), float(x)


def _sentinel1_pixel_to_latlon(image_path: str, px: float, py: float):
    try:
        from .geolocation import extract_sentinel1_coords
    except ImportError:
        try: from main.geolocation import extract_sentinel1_coords
        except ImportError: return None, None
    try:
        coords = extract_sentinel1_coords(image_path, px=px, py=py)
        if coords is not None: return coords
    except Exception: pass
    return None, None


def _try_extract_timestamp(image_path: str):
    """Extract SAR acquisition time from Sentinel-1 naming metadata only.

    A filesystem modification time is deliberately not used as an acquisition
    timestamp: it describes local file handling, not when the satellite image
    was acquired. Returning None lets the caller explicitly mark acquisition
    time as unavailable rather than silently contaminating AIS correlation.
    """
    name = Path(image_path).name
    patterns = [
        r"(?P<start>\d{8}T\d{6})_(?P<end>\d{8}T\d{6})",
        r"(?P<start>\d{8}T\d{6})",
    ]
    for pattern in patterns:
        m = re.search(pattern, name)
        if m:
            value = m.group("start")
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
    return None


def _normalize_sar_tile(tile):
    import numpy as np
    tile = np.asarray(tile, dtype=np.float32)
    tile = np.nan_to_num(tile, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = np.percentile(tile, [2.0, 98.0])
    if hi <= lo: lo, hi = float(tile.min()), float(tile.max())
    out = np.zeros(tile.shape, dtype=np.uint8) if hi <= lo else np.clip((tile - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
    return np.stack((out, out, out), axis=-1)


def _tile_starts(length: int, tile_size: int, overlap: float):
    if length <= tile_size: return [0]
    step = max(1, int(tile_size * (1.0 - overlap)))
    starts = list(range(0, length - tile_size + 1, step))
    final = length - tile_size
    if starts[-1] != final: starts.append(final)
    return starts


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1, ix2, iy2 = max(ax1,bx1), max(ay1,by1), min(ax2,bx2), min(ay2,by2)
    inter = max(0.0, ix2-ix1) * max(0.0, iy2-iy1)
    if inter <= 0: return 0.0
    aa = max(0.0, ax2-ax1) * max(0.0, ay2-ay1); ab = max(0.0, bx2-bx1) * max(0.0, by2-by1)
    return inter / max(1e-9, aa + ab - inter)


def _global_nms(detections, iou_threshold: float):
    ordered = sorted(detections, key=lambda d: d["confidence"], reverse=True)
    kept = []
    for det in ordered:
        if all(_iou(det["bbox_px"], prev["bbox_px"]) < iou_threshold for prev in kept): kept.append(det)
    return kept


def detect_hulls(image_path: str, conf: float = CONF_THRESHOLD, iou: float = IOU_THRESHOLD, timestamp: str = None) -> list:
    model = _get_model()
    ts = timestamp or _try_extract_timestamp(image_path)
    try: import rasterio
    except ImportError as exc: raise RuntimeError("rasterio is required for SAR ship detection") from exc

    path = Path(image_path)
    with rasterio.open(str(path)) as src:
        width, height, count = src.width, src.height, src.count
        if count < 1: raise ValueError(f"SAR image contains no raster bands: {path}")
        raw = []
        if count >= 3:
            results = model.predict(str(path), imgsz=800, conf=conf, iou=iou, verbose=False)
            for result in results:
                for box in result.boxes:
                    x1,y1,x2,y2 = box.xyxy[0].tolist()
                    raw.append({"bbox_px":[float(x1),float(y1),float(x2),float(y2)],"confidence":float(box.conf.item())})
        else:
            for y0 in _tile_starts(height,TILE_SIZE,TILE_OVERLAP):
                for x0 in _tile_starts(width,TILE_SIZE,TILE_OVERLAP):
                    tw,th=min(TILE_SIZE,width-x0),min(TILE_SIZE,height-y0)
                    tile=src.read(1,window=rasterio.windows.Window(x0,y0,tw,th))
                    results=model.predict(_normalize_sar_tile(tile),imgsz=800,conf=conf,iou=iou,verbose=False)
                    for result in results:
                        for box in result.boxes:
                            x1,y1,x2,y2=box.xyxy[0].tolist()
                            raw.append({"bbox_px":[float(x1)+x0,float(y1)+y0,float(x2)+x0,float(y2)+y0],"confidence":float(box.conf.item())})

    raw=_global_nms(raw,iou)
    transform,crs=_try_read_geotransform(image_path)
    detections=[]
    for det in raw:
        x1,y1,x2,y2=det["bbox_px"]; cx,cy=(x1+x2)/2.0,(y1+y2)/2.0
        lat=lon=None
        if transform is not None: lat,lon=_pixel_to_latlon(transform,crs,cx,cy)
        else: lat,lon=_sentinel1_pixel_to_latlon(image_path,cx,cy)
        detections.append({"bbox_px":[round(x1,1),round(y1,1),round(x2,1),round(y2,1)],"confidence":round(det["confidence"],3),"lat":round(lat,6) if lat is not None else None,"lon":round(lon,6) if lon is not None else None,"timestamp":ts})
    return detections


if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("image"); p.add_argument("--conf",type=float,default=CONF_THRESHOLD); p.add_argument("--iou",type=float,default=IOU_THRESHOLD); p.add_argument("--timestamp",default=None); p.add_argument("--json",default=None); args=p.parse_args()
    dets=detect_hulls(args.image,conf=args.conf,iou=args.iou,timestamp=args.timestamp)
    print(f"\n{args.image}: {len(dets)} ship(s) detected")
    for d in dets:
        geo=f"lat={d['lat']}, lon={d['lon']}" if d['lat'] is not None else "no geo metadata"
        print(f"  bbox={d['bbox_px']} conf={d['confidence']} {geo} ts={d['timestamp']}")
    if args.json: Path(args.json).write_text(json.dumps(dets,indent=2)); print(f"\nWrote {args.json}")
