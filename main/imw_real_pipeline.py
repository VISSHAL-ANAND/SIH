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

from .predict_and_classify import load_model, predict_and_classify
from .ship_detection_module import detect_hulls, _try_extract_timestamp
from .ais_matcher import load_ais_data, match_all_hulls, assess_ais_coverage, AIS_CSV_PATH
from .geolocation import extract_geotiff_coords, compute_image_bounds
from .vessel_history import analyze_vessel_history, history_to_dict
from .vessel_association import score_vessel_association, association_to_dict
from .trajectory_evidence import analyze_trajectory, trajectory_to_dict
from .drift_backtrack import backtrack_spill, drift_to_dict
from .evidence_fusion import fuse_evidence, fusion_to_dict


def load_rgb_image(path: str | Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


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
        # Explicit user-provided approximation; never presented as satellite-derived.
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

    # AIS CSV timestamps are naive; normalize everything to naive UTC.
    normalized = ais_df.copy()
    normalized["timestamp"] = normalized["timestamp"].dt.tz_localize(None)
    normalized_hulls = [
        datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        if isinstance(ts, str) else ts.replace(tzinfo=None)
        for ts in timestamps
    ]
    min_time = min(normalized_hulls)
    max_time = max(normalized_hulls)
    window = normalized[
        (normalized["timestamp"] >= min_time - np.timedelta64(int(time_hours * 3600), "s"))
        & (normalized["timestamp"] <= max_time + np.timedelta64(int(time_hours * 3600), "s"))
    ].copy()

    if window.empty:
        return window

    masks = []
    for hull in hulls:
        distances = haversine_km(
            hull["lat"], hull["lon"],
            window["lat"].to_numpy(), window["lon"].to_numpy()
        )
        masks.append(distances <= radius_km)

    return window.loc[np.logical_or.reduce(masks)].copy() if masks else window.iloc[0:0].copy()


def run_real_pipeline(
    image_path: str | Path,
    center_lat: float | None = None,
    center_lon: float | None = None,
    use_ais: bool = True,
) -> dict[str, Any]:
    """Run the real Phase-2 chain. No synthetic hulls, AIS, RF, or coordinates."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"SAR image not found: {path}")

    image_rgb = load_rgb_image(path)
    timestamp = image_timestamp(path)

    model = load_model()
    slick = predict_and_classify(model, image_rgb)

    components = []
    for component in slick["components"]:
        item = dict(component)
        geo = geolocate_pixel(
            path, component["centroid_x"], component["centroid_y"],
            center_lat, center_lon
        )
        item["geolocation"] = (
            {"lat": geo[0], "lon": geo[1], "source": geo[2]} if geo else None
        )
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
            hull_dicts = []
            for idx, hull in enumerate(georef_hulls):
                ts = datetime.fromisoformat(hull["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None)
                hull_dicts.append({
                    "hull_id": idx,
                    "lat": hull["lat"],
                    "lon": hull["lon"],
                    "timestamp": ts,
                })
            for hull_dict in hull_dicts:
                result = match_all_hulls([hull_dict], relevant)[0]
                coverage = assess_ais_coverage(
                    ais_df,
                    hull_dict["lat"],
                    hull_dict["lon"],
                    hull_dict["timestamp"],
                )
                history = None
                if result.has_ais_match and result.matched_mmsi:
                    history = analyze_vessel_history(
                        ais_df,
                        result.matched_mmsi,
                        hull_dict["lat"],
                        hull_dict["lon"],
                        hull_dict["timestamp"],
                    )
                ais_matches.append({
                    "hull_id": result.hull_id,
                    "has_ais_match": result.has_ais_match,
                    "matched_mmsi": result.matched_mmsi,
                    "matched_vessel_name": result.matched_vessel_name,
                    "distance_km": result.distance_km,
                    "time_diff_hours": result.time_diff_hours,
                    "suspicion_score": result.suspicion_score,
                    "reason": result.reason,
                    "coverage_status": coverage.status,
                    "coverage_confidence": coverage.coverage_confidence,
                    "coverage_reason": coverage.reason,
                    "vessel_history": history_to_dict(history) if history else None,
                    "association": association_to_dict(score_vessel_association(result.hull_id, result.matched_mmsi, result.matched_vessel_name, result.distance_km, result.time_diff_hours, history.to_dict() if False else (history_to_dict(history) if history else None))),
                    "trajectory": trajectory_to_dict(analyze_trajectory(ais_df, result.matched_mmsi, hull_dict["lat"], hull_dict["lon"], hull_dict["timestamp"])) if result.has_ais_match and result.matched_mmsi else None,
                    "evidence_fusion": fusion_to_dict(fuse_evidence(
                        max(0.0, 1.0 - result.distance_km / 10.0) if result.distance_km is not None else None,
                        max(0.0, 1.0 - result.time_diff_hours / 6.0) if result.time_diff_hours is not None else None,
                        history.evidence_strength if history else None,
                        analyze_trajectory(ais_df, result.matched_mmsi, hull_dict["lat"], hull_dict["lon"], hull_dict["timestamp"]).trajectory_score if result.has_ais_match and result.matched_mmsi else None,
                        None,
                    )),
                })
        else:
            ais_source_status = "UNAVAILABLE"

    # Drift backtracking waits for authorized current/wind observations; no environmental values are invented.
    drift = {
        "status": "AWAITING_ENVIRONMENTAL_DATA",
        "origin_lat": None, "origin_lon": None, "uncertainty_km": None,
        "steps": [], "assumptions": [],
        "reason": "Current and wind observations are required before estimating a spill origin zone.",
    }

    return {
        "pipeline": {
            "status": "completed",
            "data_integrity": "REAL_ONLY",
            "stages": ["SAR", "SLICK_SEGMENTATION", "GEOLOCATION", "HULL_DETECTION", "AIS_CORRELATION"],
        },
        "sar": {
            "filename": path.name,
            "acquisition_timestamp": timestamp,
            "georeferenced": path.suffix.lower() in {".tif", ".tiff"},
        },
        "slicks": {
            "count": len(components),
            "linear_count": slick["num_linear"],
            "blob_count": slick["num_blob"],
            "components": components,
        },
        "hulls": {
            "count": len(hulls),
            "georeferenced_count": len(georef_hulls),
            "detections": hulls,
        },
        "drift": drift,
        "ais": {
            "source_status": ais_source_status,
            "matches": ais_matches,
            "interpretation": "Local AIS activity does not by itself prove an individual vessel disabled AIS. Vessel-history continuity is required before a dark-vessel claim.",
        },
        "rf": {
            "status": "NOT_IMPLEMENTED",
            "data_integrity": "NO_RF_DATA_INJECTED",
        },
    }
