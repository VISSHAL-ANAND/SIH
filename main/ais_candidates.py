"""Multi-candidate AIS search for IMW investigations.

Unlike the legacy single-best matcher, this module retains every distinct MMSI
with an AIS observation inside the configured spatial/temporal window. It does
not infer responsibility or an AIS shutdown from absence alone.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from .ais_matcher import haversine_km, DISTANCE_TOLERANCE_KM, TIME_TOLERANCE_HOURS


def find_ais_candidates(
    hull_lat: float,
    hull_lon: float,
    hull_time: datetime,
    ais_df: pd.DataFrame,
    hull_id: int = 0,
    radius_km: float = DISTANCE_TOLERANCE_KM,
    time_hours: float = TIME_TOLERANCE_HOURS,
) -> list[dict[str, Any]]:
    """Return all distinct AIS vessels observed near a SAR-detected hull.

    For each MMSI, the closest observation to the SAR hull is retained. Results
    are ordered by distance, then temporal separation. Empty results are an
    explicit lack of observed AIS candidates, not proof of a dark vessel.
    """
    if ais_df is None or ais_df.empty:
        return []

    frame = ais_df.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "lat", "lon", "mmsi"])
    if frame.empty:
        return []

    event_time = pd.Timestamp(hull_time).tz_localize(None) if pd.Timestamp(hull_time).tzinfo else pd.Timestamp(hull_time)
    timestamps = frame["timestamp"]
    if getattr(timestamps.dt, "tz", None) is not None:
        timestamps = timestamps.dt.tz_localize(None)
    frame["_time"] = timestamps
    frame["temporal_delta_hours"] = (frame["_time"] - event_time).abs().dt.total_seconds() / 3600.0
    frame = frame[frame["temporal_delta_hours"] <= time_hours].copy()
    if frame.empty:
        return []

    frame["spatial_distance_km"] = haversine_km(
        hull_lat, hull_lon, frame["lat"].to_numpy(), frame["lon"].to_numpy()
    )
    frame = frame[frame["spatial_distance_km"] <= radius_km].copy()
    if frame.empty:
        return []

    frame["mmsi"] = frame["mmsi"].astype(str)
    frame = frame.sort_values(["spatial_distance_km", "temporal_delta_hours"])
    frame = frame.drop_duplicates(subset=["mmsi"], keep="first")

    candidates = []
    for _, row in frame.iterrows():
        name = row.get("vessel_name")
        candidates.append({
            "hull_id": hull_id,
            "mmsi": str(row["mmsi"]),
            "vessel_name": None if pd.isna(name) else str(name).strip(),
            "spatial_distance_km": round(float(row["spatial_distance_km"]), 3),
            "temporal_delta_min": round(float(row["temporal_delta_hours"]) * 60.0, 2),
            "ais_observation_time": row["_time"].isoformat(),
            "ais_candidate_status": "OBSERVED_NEAR_SAR_HULL",
            "responsibility_status": "NOT_ESTABLISHED",
        })
    return candidates
