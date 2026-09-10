"""
IMW Phase 2 — real SAR pipeline adapter.

Connects the existing trained components without injecting synthetic results:
SAR U-Net -> slick components -> geolocation -> YOLO hull detection -> AIS matching.
Missing models/data sources are reported explicitly.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .predict_and_classify import load_model, predict_and_classify, predict_mask
from .ship_detection_module import detect_hulls, _try_extract_timestamp
from .ais_matcher import load_ais_data, match_all_hulls, assess_ais_coverage, AIS_CSV_PATH
from .geolocation import extract_geotiff_coords, compute_image_bounds
from .vessel_history import analyze_vessel_history, history_to_dict
from .vessel_association import score_vessel_association, association_to_dict
from .trajectory_evidence import analyze_trajectory, trajectory_to_dict
from .evidence_fusion import fuse_evidence, fusion_to_dict
from .incident_package import CandidateVessel, build_incident_package, incident_to_dict
from .rf_corroboration import corroborate_rf


def load_rgb_image(path: str | Path) -> np.ndarray:
    """Compatibility path for ordinary PNG/JPG inputs."""
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _normalize_tile(data: np.ndarray) -> np.ndarray:
    """Convert a raster tile to stable uint8 RGB without inventing geospatial data."""
    arr = np.asarray(data, dtype=np.float32)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros(arr.shape, dtype=np.uint8)
    out = np.zeros(arr.shape, dtype=np.float32)
    for band in range(arr.shape[2]):
        channel = arr[:, :, band]
        valid = np.isfinite(channel)
        if not valid.any():
            continue
        lo, hi = np.percentile(channel[valid], [2, 98])
        if hi <= lo:
            lo = float(np.min(channel[valid]))
            hi = float(np.max(channel[valid]))
        if hi > lo:
            out[:, :, band] = np.clip((np.nan_to_num(channel, nan=lo) - lo) / (hi - lo), 0, 1) * 255
    return out.astype(np.uint8)


def load_tiled_rgb(path: str | Path, tile_size: int = 1024, overlap: int = 128):
    """Yield memory-bounded RGB tiles as ``(x, y, array)``."""
    if tile_size <= 0 or overlap < 0 or overlap >= tile_size:
        raise ValueError("tile_size must be > 0 and 0 <= overlap < tile_size")
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("rasterio is required for tiled GeoTIFF ingestion") from exc

    step = tile_size - overlap
    with rasterio.open(path) as src:
        if src.count < 1:
            raise ValueError("SAR raster contains no bands")
        for y in range(0, src.height, step):
            for x in range(0, src.width, step):
                width = min(tile_size, src.width - x)
                height = min(tile_size, src.height - y)
                window = rasterio.windows.Window(x, y, width, height)
                bands = min(3, src.count)
                data = src.read(indexes=list(range(1, bands + 1)), window=window)
                data = np.moveaxis(data, 0, -1)
                if bands == 1:
                    data = np.repeat(data, 3, axis=2)
                elif bands == 2:
                    data = np.concatenate([data, data[:, :, :1]], axis=2)
                yield x, y, _normalize_tile(data)


def image_timestamp(path: str | Path) -> str:
    ts = _try_extract_timestamp(str(path))
    if ts is None:
        raise ValueError("Could not determine SAR acquisition timestamp")
    return ts


def geolocate_pixel(path: str | Path, x: float, y: float,
                     center_lat: float | None = None,
                     center_lon: float | None = None) -> tuple[float, float, str] | None:
    geo = extract_geotiff_coords(path, x, y)
    if geo is not None:
        return geo[0], geo[1], "GeoTIFF metadata"
    if center_lat is not None and center_lon is not None:
        bounds = compute_image_bounds(center_lat, center_lon)
        lat, lon = bounds["centroid"]
        return float(lat), float(lon), "user-supplied image center"
    return None


def filter_ais_for_hulls(ais_df, hulls: list[dict], radius_km: float = 25.0,
                         time_hours: float = 6.0):
    if ais_df.empty or not hulls:
        return ais_df.iloc[0:0].copy()
    from .ais_matcher import haversine_km
    timestamps = [h["timestamp"] for h in hulls if h.get("timestamp")]
    if not timestamps:
        return ais_df.iloc[0:0].copy()
    normalized = ais_df.copy()
    normalized["timestamp"] = normalized["timestamp"].dt.tz_localize(None)
    normalized_hulls = [
        datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        if isinstance(ts, str) else ts.replace(tzinfo=None)
        for ts in timestamps
    ]
    min_time = min(normalized_hulls)
    max_time = max(normalized_hulls)
    delta = np.timedelta64(int(time_hours * 3600), "s")
    window = normalized[(normalized["timestamp"] >= min_time - delta) & (normalized["timestamp"] <= max_time + delta)].copy()
    if window.empty:
        return window
    masks = []
    for hull in hulls:
        distances = haversine_km(hull["lat"], hull["lon"], window["lat"].to_numpy(), window["lon"].to_numpy())
        masks.append(distances <= radius_km)
    return window.loc[np.logical_or.reduce(masks)].copy() if masks else window.iloc[0:0].copy()


def build_incident_id(timestamp: datetime) -> str:
    return f"IMW-{timestamp.strftime('%Y%m%d-%H%M%S')}"


def _run_slick_inference(path: Path, model):
    """Run full-scene inference, tiling GeoTIFFs and stitching masks by overlap voting."""
    if path.suffix.lower() not in {".tif", ".tiff"}:
        image_rgb = load_rgb_image(path)
        return predict_and_classify(model, image_rgb), "FULL_IMAGE"

    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("rasterio is required for GeoTIFF inference") from exc

    with rasterio.open(path) as src:
        height, width = src.height, src.width
    mask_sum = np.zeros((height, width), dtype=np.float32)
    mask_count = np.zeros((height, width), dtype=np.uint16)

    for x, y, tile in load_tiled_rgb(path):
        mask = predict_mask(model, tile)
        h, w = mask.shape
        mask_sum[y:y + h, x:x + w] += mask
        mask_count[y:y + h, x:x + w] += 1

    stitched = (mask_sum >= np.maximum(mask_count, 1) / 2.0).astype(np.uint8)
    from .shape_classifier import classify_slick_shape, components_to_dicts
    raw_components = classify_slick_shape(stitched)
    component_dicts = components_to_dicts(raw_components)
    return {
        "predicted_mask": stitched,
        "components": component_dicts,
        "num_slicks_detected": len(component_dicts),
        "num_linear": sum(1 for c in component_dicts if c["shape_class"] == "linear"),
        "num_blob": sum(1 for c in component_dicts if c["shape_class"] == "blob"),
    }, "TILED_GEOTIFF"


def run_real_pipeline(image_path: str | Path, center_lat: float | None = None,
                      center_lon: float | None = None, use_ais: bool = True) -> dict[str, Any]:
    """Run the real Phase-2 chain. No synthetic hulls, AIS, RF, or coordinates."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"SAR image not found: {path}")

    timestamp = image_timestamp(path)
    model = load_model()
    slick, inference_mode = _run_slick_inference(path, model)

    components = []
    for component in slick["components"]:
        item = dict(component)
        geo = geolocate_pixel(path, component["centroid_x"], component["centroid_y"], center_lat, center_lon)
        item["geolocation"] = {"lat": geo[0], "lon": geo[1], "source": geo[2]} if geo else None
        components.append(item)

    hulls = detect_hulls(str(path))
    georef_hulls = [h for h in hulls if h.get("lat") is not None and h.get("lon") is not None]

    ais_matches = []
    ais_source_status = "NOT_REQUESTED"
    if use_ais:
        if not georef_hulls:
            ais_source_status = "NO_GEOREFERENCED_HULLS"
        elif Path(AIS_CSV_PATH).exists():
            ais_source_status = "REAL_MARINECADASTRE"
            ais_df = load_ais_data(AIS_CSV_PATH)
            relevant = filter_ais_for_hulls(ais_df, georef_hulls)
            for idx, hull in enumerate(georef_hulls):
                ts = datetime.fromisoformat(hull["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None)
                hull_dict = {"hull_id": idx, "lat": hull["lat"], "lon": hull["lon"], "timestamp": ts}
                result = match_all_hulls([hull_dict], relevant)[0]
                coverage = assess_ais_coverage(ais_df, hull_dict["lat"], hull_dict["lon"], hull_dict["timestamp"])
                history = analyze_vessel_history(ais_df, result.matched_mmsi, hull_dict["lat"], hull_dict["lon"], hull_dict["timestamp"]) if result.has_ais_match and result.matched_mmsi else None
                trajectory = analyze_trajectory(ais_df, result.matched_mmsi, hull_dict["lat"], hull_dict["lon"], hull_dict["timestamp"]) if result.has_ais_match and result.matched_mmsi else None
                ais_matches.append({
                    "hull_id": result.hull_id, "has_ais_match": result.has_ais_match,
                    "matched_mmsi": result.matched_mmsi, "matched_vessel_name": result.matched_vessel_name,
                    "distance_km": result.distance_km, "time_diff_hours": result.time_diff_hours,
                    "suspicion_score": result.suspicion_score, "reason": result.reason,
                    "coverage_status": coverage.status, "coverage_confidence": coverage.coverage_confidence,
                    "coverage_reason": coverage.reason,
                    "vessel_history": history_to_dict(history) if history else None,
                    "association": association_to_dict(score_vessel_association(result.hull_id, result.matched_mmsi, result.matched_vessel_name, result.distance_km, result.time_diff_hours, history_to_dict(history) if history else None)),
                    "trajectory": trajectory_to_dict(trajectory) if trajectory else None,
                    "evidence_fusion": fusion_to_dict(fuse_evidence(
                        max(0.0, 1.0 - result.distance_km / 10.0) if result.distance_km is not None else None,
                        max(0.0, 1.0 - result.time_diff_hours / 6.0) if result.time_diff_hours is not None else None,
                        history.evidence_strength if history else None, trajectory.trajectory_score if trajectory else None, None,
                    )),
                })
        else:
            ais_source_status = "UNAVAILABLE"

    drift = {"status": "AWAITING_ENVIRONMENTAL_DATA", "origin_lat": None, "origin_lon": None, "uncertainty_km": None, "steps": [], "assumptions": [], "reason": "Current and wind observations are required before estimating a spill origin zone."}
    candidate_objects = [CandidateVessel(mmsi=m.get("matched_mmsi"), vessel_name=m.get("matched_vessel_name"), association=m.get("evidence_fusion") or m.get("association") or {}, history=m.get("vessel_history"), trajectory=m.get("trajectory")) for m in ais_matches]
    rf_result = corroborate_rf([], 0.0, 0.0)
    package = build_incident_package(
        incident_id=build_incident_id(datetime.fromisoformat(timestamp.replace("Z", "+00:00"))),
        detection={"timestamp": timestamp, "source": "SAR_ANALYSIS"}, geolocation={"hulls": georef_hulls},
        spill={"count": len(components), "components": components}, ais={"source_status": ais_source_status, "matches": ais_matches},
        environmental={"status": "NOT_AVAILABLE", "reason": "No environmental observations supplied to this run."}, drift=drift, rf=rf_result,
        candidates=candidate_objects, limitations=["RF observations were not supplied.", "Environmental observations are not yet supplied."],
    )
    return {
        "incident": incident_to_dict(package),
        "pipeline": {"status": "completed", "data_integrity": "REAL_ONLY", "stages": ["SAR", "SLICK_SEGMENTATION", "GEOLOCATION", "HULL_DETECTION", "AIS_CORRELATION", "INCIDENT_PACKAGING"], "inference_mode": inference_mode},
        "sar": {"filename": path.name, "acquisition_timestamp": timestamp, "georeferenced": path.suffix.lower() in {".tif", ".tiff"}, "inference_mode": inference_mode},
        "slicks": {"count": len(components), "linear_count": slick["num_linear"], "blob_count": slick["num_blob"], "components": components},
        "hulls": {"count": len(hulls), "georeferenced_count": len(georef_hulls), "detections": hulls}, "drift": drift,
        "ais": {"source_status": ais_source_status, "matches": ais_matches, "interpretation": "Local AIS activity does not by itself prove an individual vessel disabled AIS. Vessel-history continuity is required before a dark-vessel claim."},
        "rf": rf_result,
    }
