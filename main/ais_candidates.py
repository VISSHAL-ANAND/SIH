"""Multi-candidate AIS correlation for IMW investigations.

The candidate engine keeps distinct MMSIs observed inside a spatial/temporal
window around a SAR-detected hull. It exposes the strongest raw AIS evidence
for downstream history, trajectory and ranking modules without claiming that
any vessel caused the spill.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .ais_matcher import haversine_km, DISTANCE_TOLERANCE_KM, TIME_TOLERANCE_HOURS


def _optional_value(row: pd.Series, *names: str):
    """Return the first present, non-null AIS field from a row."""
    for name in names:
        if name in row.index:
            value = row[name]
            if not pd.isna(value):
                return value
    return None


def _as_float(value):
    if value is None:
        return None
    try:
        value = float(value)
        return round(value, 3)
    except (TypeError, ValueError):
        return None


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

    Matching requires an AIS observation to satisfy BOTH spatial and temporal
    tolerances. For each MMSI, the observation with the smallest combined
    spatial/temporal separation is retained. Empty results mean that no AIS
    candidate was observed in the supplied dataset; they do not prove a dark
    vessel or intentional AIS shutdown.
    """
    if ais_df is None or ais_df.empty:
        return []

    required = {"timestamp", "lat", "lon", "mmsi"}
    if not required.issubset(ais_df.columns):
        return []

    frame = ais_df.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["lat"] = pd.to_numeric(frame["lat"], errors="coerce")
    frame["lon"] = pd.to_numeric(frame["lon"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "lat", "lon", "mmsi"])
    if frame.empty:
        return []

    event_time = pd.Timestamp(hull_time)
    if event_time.tzinfo is not None:
        event_time = event_time.tz_localize(None)

    timestamps = frame["timestamp"]
    if getattr(timestamps.dt, "tz", None) is not None:
        timestamps = timestamps.dt.tz_localize(None)
    frame["_time"] = timestamps

    frame["temporal_delta_hours"] = (
        frame["_time"] - event_time
    ).abs().dt.total_seconds() / 3600.0
    frame = frame[frame["temporal_delta_hours"] <= float(time_hours)].copy()
    if frame.empty:
        return []

    frame["spatial_distance_km"] = haversine_km(
        hull_lat,
        hull_lon,
        frame["lat"].to_numpy(),
        frame["lon"].to_numpy(),
    )
    frame = frame[frame["spatial_distance_km"] <= float(radius_km)].copy()
    if frame.empty:
        return []

    frame["mmsi"] = frame["mmsi"].astype(str)

    # Prefer spatial proximity, then temporal proximity. This makes the
    # selected observation deterministic and easy to explain to an operator.
    frame = frame.sort_values(
        ["mmsi", "spatial_distance_km", "temporal_delta_hours"]
    )
    frame = frame.drop_duplicates(subset=["mmsi"], keep="first")

    candidates: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        name = _optional_value(row, "vessel_name", "shipname", "name")
        candidates.append(
            {
                "hull_id": hull_id,
                "mmsi": str(row["mmsi"]),
                "vessel_name": str(name).strip() if name is not None else None,
                "spatial_distance_km": round(float(row["spatial_distance_km"]), 3),
                "temporal_delta_min": round(float(row["temporal_delta_hours"]) * 60.0, 2),
                "ais_observation_time": row["_time"].isoformat(),
                "ais_lat": round(float(row["lat"]), 6),
                "ais_lon": round(float(row["lon"]), 6),
                "sog_knots": _as_float(_optional_value(row, "sog", "speed")),
                "cog_degrees": _as_float(_optional_value(row, "cog", "course")),
                "heading_degrees": _as_float(_optional_value(row, "heading")),
                "imo": _optional_value(row, "imo"),
                "call_sign": _optional_value(row, "call_sign", "callsign"),
                "vessel_type": _optional_value(row, "vessel_type", "ship_type"),
                "navigation_status": _optional_value(row, "status", "navigation_status"),
                "ais_candidate_status": "OBSERVED_NEAR_SAR_HULL",
                "responsibility_status": "NOT_ESTABLISHED",
            }
        )

    return sorted(
        candidates,
        key=lambda item: (
            item["spatial_distance_km"],
            item["temporal_delta_min"],
            item["mmsi"],
        ),
    )
