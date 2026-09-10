"""IMW real SAR/AIS investigation pipeline."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .predict_and_classify import load_model, predict_and_classify, predict_mask
from .ship_detection_module import detect_hulls, _try_extract_timestamp
from .ais_matcher import load_ais_data, match_all_hulls, assess_ais_coverage, AIS_CSV_PATH
from .ais_candidates import find_ais_candidates
from .gfw_ais_provider import GFWAPIError, GFWAISProvider
from .geolocation import extract_geotiff_coords, pixel_to_latlon
from .vessel_history import analyze_vessel_history, history_to_dict
from .vessel_association import score_vessel_association, association_to_dict
from .trajectory_evidence import analyze_trajectory, trajectory_to_dict
from .evidence_fusion import fuse_evidence, fusion_to_dict
from .candidate_ranking import rank_candidates, ranked_to_dict
from .incident_package import CandidateVessel, build_incident_package, incident_to_dict
from .spill_vessel_graph import build_spill_vessel_graph
from .rf_corroboration import corroborate_rf
from .drift_analysis import estimate_source_zone, drift_to_dict


def load_rgb_image(path: str | Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _normalize_tile(data: np.ndarray) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32)
    if not np.isfinite(arr).any():
        return np.zeros(arr.shape, dtype=np.uint8)
    out = np.zeros(arr.shape, dtype=np.float32)
    for band in range(arr.shape[2]):
        channel = arr[:, :, band]
        valid = np.isfinite(channel)
        if not valid.any():
            continue
        lo, hi = np.percentile(channel[valid], [2, 98])
        if hi <= lo:
            lo, hi = float(np.min(channel[valid])), float(np.max(channel[valid]))
        if hi > lo:
            out[:, :, band] = np.clip((np.nan_to_num(channel, nan=lo) - lo) / (hi - lo), 0, 1) * 255
    return out.astype(np.uint8)


def load_tiled_rgb(path: str | Path, tile_size: int = 1024, overlap: int = 128):
    if tile_size <= 0 or overlap < 0 or overlap >= tile_size:
        raise ValueError("tile_size must be > 0 and 0 <= overlap < tile_size")
    import rasterio
    step = tile_size - overlap
    with rasterio.open(path) as src:
        if src.count < 1:
            raise ValueError("SAR raster contains no bands")
        for y in range(0, src.height, step):
            for x in range(0, src.width, step):
                width, height = min(tile_size, src.width - x), min(tile_size, src.height - y)
                data = src.read(indexes=list(range(1, min(3, src.count) + 1)), window=rasterio.windows.Window(x, y, width, height))
                data = np.moveaxis(data, 0, -1)
                if data.shape[2] == 1:
                    data = np.repeat(data, 3, axis=2)
                elif data.shape[2] == 2:
                    data = np.concatenate([data, data[:, :, :1]], axis=2)
                yield x, y, _normalize_tile(data)


def image_timestamp(path: str | Path) -> str:
    ts = _try_extract_timestamp(str(path))
    if ts is None:
        raise ValueError("Could not determine SAR acquisition timestamp")
    return ts


def geolocate_pixel(path: str | Path, x: float, y: float, center_lat: float | None = None, center_lon: float | None = None):
    geo = extract_geotiff_coords(path, x, y)
    if geo is not None:
        return geo[0], geo[1], "REAL_GEOTIFF_PIXEL_CENTER"
    if center_lat is not None and center_lon is not None:
        try:
            with Image.open(path) as image:
                width_px, height_px = image.size
        except Exception:
            width_px, height_px = 512, 512
        lat, lon = pixel_to_latlon(x, y, float(center_lat), float(center_lon), width_px=width_px, height_px=height_px, meters_per_pixel=10.0)
        return float(lat), float(lon), "ESTIMATED_USER_CENTER_PLUS_10M_GSD"
    return None


def filter_ais_for_hulls(ais_df, hulls: list[dict], radius_km: float = 25.0, time_hours: float = 6.0):
    if ais_df.empty or not hulls:
        return ais_df.iloc[0:0].copy()
    from .ais_matcher import haversine_km
    timestamps = [h["timestamp"] for h in hulls if h.get("timestamp")]
    if not timestamps:
        return ais_df.iloc[0:0].copy()
    normalized = ais_df.copy()
    normalized["timestamp"] = normalized["timestamp"].dt.tz_localize(None)
    normalized_hulls = [datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None) if isinstance(ts, str) else ts.replace(tzinfo=None) for ts in timestamps]
    min_time, max_time = min(normalized_hulls), max(normalized_hulls)
    delta = np.timedelta64(int(time_hours * 3600), "s")
    window = normalized[(normalized["timestamp"] >= min_time - delta) & (normalized["timestamp"] <= max_time + delta)].copy()
    if window.empty:
        return window
    masks = [haversine_km(h["lat"], h["lon"], window["lat"].to_numpy(), window["lon"].to_numpy()) <= radius_km for h in hulls]
    return window.loc[np.logical_or.reduce(masks)].copy() if masks else window.iloc[0:0].copy()


def build_incident_id(timestamp: datetime) -> str:
    return f"IMW-{timestamp.strftime('%Y%m%d-%H%M%S')}"


def _run_slick_inference(path: Path, model):
    if path.suffix.lower() not in {".tif", ".tiff"}:
        return predict_and_classify(model, load_rgb_image(path)), "FULL_IMAGE"
    import rasterio
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
    components = components_to_dicts(classify_slick_shape(stitched))
    return {"predicted_mask": stitched, "components": components, "num_slicks_detected": len(components), "num_linear": sum(c["shape_class"] == "linear" for c in components), "num_blob": sum(c["shape_class"] == "blob" for c in components)}, "TILED_GEOTIFF"


def _parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _candidate_evidence(hull: dict, candidate: dict, coverage, ais_df, detection_time: datetime) -> dict:
    mmsi = candidate.get("mmsi")
    history = trajectory = None
    if mmsi:
        history = history_to_dict(analyze_vessel_history(ais_df, mmsi, hull["lat"], hull["lon"], detection_time))
        trajectory = trajectory_to_dict(analyze_trajectory(ais_df, mmsi, hull["lat"], hull["lon"], detection_time))
    distance_km = candidate.get("spatial_distance_km")
    time_diff_hours = None if candidate.get("temporal_delta_min") is None else float(candidate["temporal_delta_min"]) / 60.0
    hull_id = candidate.get("hull_id", hull.get("hull_id", 0))
    association = association_to_dict(score_vessel_association(hull_id, mmsi, candidate.get("vessel_name"), distance_km, time_diff_hours, history, coverage.status))
    fusion = fusion_to_dict(fuse_evidence(max(0.0, 1.0 - distance_km / 10.0) if distance_km is not None else None, max(0.0, 1.0 - time_diff_hours / 6.0) if time_diff_hours is not None else None, history.get("evidence_strength") if history else None, trajectory.get("trajectory_score") if trajectory else None, None))
    return {"hull_id": hull_id, "has_ais_match": bool(mmsi), "matched_mmsi": mmsi, "matched_vessel_name": candidate.get("vessel_name"), "distance_km": distance_km, "time_diff_hours": time_diff_hours, "spatial_distance_km": distance_km, "temporal_delta_min": candidate.get("temporal_delta_min"), "suspicion_score": 0.0, "reason": "Observed AIS candidate retained for investigation; responsibility is not established.", "coverage_status": coverage.status, "coverage_confidence": coverage.coverage_confidence, "coverage_reason": coverage.reason, "vessel_history": history, "trajectory": trajectory, "association": association, "evidence_fusion": fusion, "responsibility_status": "NOT_ESTABLISHED", "evidence_time_anchor": detection_time.isoformat() + "Z"}


def _unresolved_candidate(hull_id: int, coverage, detection_time: datetime) -> dict:
    return {"hull_id": hull_id, "has_ais_match": False, "matched_mmsi": None, "matched_vessel_name": None, "distance_km": None, "time_diff_hours": None, "spatial_distance_km": None, "temporal_delta_min": None, "suspicion_score": 0.0, "reason": "No AIS candidate observed within the configured search window.", "coverage_status": coverage.status, "coverage_confidence": coverage.coverage_confidence, "coverage_reason": coverage.reason, "vessel_history": None, "trajectory": None, "association": association_to_dict(score_vessel_association(hull_id, None, None, None, None, None, coverage.status)), "evidence_fusion": fusion_to_dict(fuse_evidence(None, None, None, None, None)), "responsibility_status": "NOT_ESTABLISHED", "evidence_time_anchor": detection_time.isoformat() + "Z"}


def _enrich_ranked_candidate(rank_item: dict | None, candidate: dict) -> dict:
    enriched = dict(candidate)
    enriched["ranking"] = rank_item or {"rank": None, "priority": "UNRANKED", "priority_score": 0.0, "evidence_confidence": "LOW", "responsibility_status": "NOT_ESTABLISHED"}
    if rank_item:
        enriched["classification"] = rank_item.get("association_classification", "UNRESOLVED")
        enriched["evidence_confidence"] = rank_item.get("evidence_confidence", "LOW")
    return enriched


def _load_ais_source(georef_hulls: list[dict], detection_time: datetime):
    """Choose GFW for current authorized access, else the documented local replay source."""
    if not georef_hulls:
        return None, "NO_GEOREFERENCED_HULLS", None

    gfw_token = os.getenv("GFW_API_ACCESS_TOKEN")
    gfw_error = None
    if gfw_token:
        try:
            gfw_df = GFWAISProvider(gfw_token).get_presence(georef_hulls, detection_time, window_hours=2.0)
            return gfw_df, "REAL_GFW_AIS_PRESENCE", None
        except GFWAPIError as exc:
            gfw_error = str(exc)

    if Path(AIS_CSV_PATH).exists():
        fallback_status = "REAL_MARINECADASTRE_REPLAY" if not gfw_error else "REAL_MARINECADASTRE_FALLBACK"
        return load_ais_data(AIS_CSV_PATH), fallback_status, gfw_error

    return None, "UNAVAILABLE", gfw_error


def run_real_pipeline(image_path: str | Path, center_lat: float | None = None, center_lon: float | None = None, use_ais: bool = True, environmental_observations: list[dict] | None = None, windage: float = 0.03, drift_uncertainty_km: float = 2.0) -> dict[str, Any]:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"SAR image not found: {path}")
    timestamp = image_timestamp(path)
    detection_time = _parse_timestamp(timestamp)
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
    ais_matches, ranked_candidates = [], []
    vessel_graph = {"status": "NO_AIS_CANDIDATES", "nodes": [], "edges": []}
    ais_source_status = "NOT_REQUESTED"
    ais_source_detail = None

    if use_ais:
        ais_df, ais_source_status, ais_source_detail = _load_ais_source(georef_hulls, detection_time)
        if ais_df is not None:
            relevant = filter_ais_for_hulls(ais_df, georef_hulls, time_hours=6.0)
            all_candidates = []
            for idx, hull in enumerate(georef_hulls):
                hull_dict = {"hull_id": idx, "lat": hull["lat"], "lon": hull["lon"], "timestamp": detection_time}
                coverage = assess_ais_coverage(ais_df, hull_dict["lat"], hull_dict["lon"], detection_time)
                matches = find_ais_candidates(hull_dict["lat"], hull_dict["lon"], detection_time, relevant, hull_id=idx, radius_km=5.0, time_hours=2.0)
                if matches:
                    all_candidates.extend(_candidate_evidence(hull_dict, c, coverage, ais_df, detection_time) for c in matches)
                else:
                    legacy = match_all_hulls([hull_dict], relevant)[0]
                    if legacy.has_ais_match:
                        all_candidates.append(_candidate_evidence(hull_dict, {"hull_id": idx, "mmsi": legacy.matched_mmsi, "vessel_name": legacy.matched_vessel_name, "spatial_distance_km": legacy.distance_km, "temporal_delta_min": None if legacy.time_diff_hours is None else legacy.time_diff_hours * 60.0}, coverage, ais_df, detection_time))
                    else:
                        all_candidates.append(_unresolved_candidate(idx, coverage, detection_time))
            ranked_dicts = ranked_to_dict(rank_candidates(all_candidates))
            ranking_by_key = {(r.get("hull_id"), r.get("mmsi")): r for r in ranked_dicts}
            ranked_candidates = [_enrich_ranked_candidate(ranking_by_key.get((c.get("hull_id"), c.get("matched_mmsi"))), c) for c in all_candidates]
            ais_matches = ranked_candidates
            vessel_graph = build_spill_vessel_graph(ranked_candidates)

    primary_location = next((c.get("geolocation") for c in components if c.get("geolocation")), None)
    drift_result = estimate_source_zone(primary_location.get("lat") if primary_location else None, primary_location.get("lon") if primary_location else None, timestamp, environmental_observations, windage=windage, uncertainty_km=drift_uncertainty_km)
    drift = drift_to_dict(drift_result)
    environmental = {"status": "AVAILABLE" if environmental_observations else "NOT_AVAILABLE", "observation_count": len(environmental_observations or []), "reason": drift_result.reason}

    candidate_objects = [CandidateVessel(mmsi=m["matched_mmsi"], vessel_name=m.get("matched_vessel_name"), association=m.get("association") or {}, history=m.get("vessel_history"), trajectory=m.get("trajectory"), ranking=m.get("ranking")) for m in ais_matches if m.get("matched_mmsi")]
    rf_result = corroborate_rf([], 0.0, 0.0)
    package = build_incident_package(incident_id=build_incident_id(detection_time), detection={"timestamp": timestamp, "source": "SAR_ANALYSIS"}, geolocation={"hulls": georef_hulls}, spill={"count": len(components), "components": components, "inference_mode": inference_mode}, ais={"source_status": ais_source_status, "source_detail": ais_source_detail, "matches": ais_matches, "candidates": ranked_candidates, "vessel_graph": vessel_graph}, environmental=environmental, drift=drift, rf=rf_result, candidates=candidate_objects)
    incident = incident_to_dict(package)
    incident["responsibility_status"] = "NOT_ESTABLISHED"
    return {"status": "success", "data_integrity": "REAL_ONLY", "inference_mode": inference_mode, "components": components, "hulls": georef_hulls, "ais_source_status": ais_source_status, "ais_source_detail": ais_source_detail, "ais_matches": ais_matches, "ranked_candidates": ranked_candidates, "vessel_graph": vessel_graph, "environmental": environmental, "drift": drift, "rf_corroboration": rf_result, "incident": incident}
