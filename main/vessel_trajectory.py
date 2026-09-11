"""Observed AIS vessel trajectory reconstruction for IMW.

Reconstructs a recent chronological AIS track and measures its relationship
with a SAR hull location. This is investigative evidence only and never
establishes spill causation or legal responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin

import pandas as pd

from .ais_matcher import haversine_km


@dataclass
class TrackPoint:
    timestamp: str
    lat: float
    lon: float
    distance_to_hull_km: float


@dataclass
class VesselTrajectory:
    mmsi: str
    points: list[TrackPoint]
    points_before: int
    points_after: int
    nearest_distance_km: float | None
    closest_timestamp: str | None
    start_distance_km: float | None
    end_distance_km: float | None
    path_min_distance_km: float | None
    path_intersects_vicinity: bool
    approaches_vicinity: bool
    status: str
    reason: str


def _prepare_vessel(ais_df: pd.DataFrame, mmsi: str) -> pd.DataFrame:
    required = {"mmsi", "timestamp", "lat", "lon"}
    if ais_df is None or ais_df.empty or not required.issubset(ais_df.columns):
        return pd.DataFrame(columns=list(required))
    vessel = ais_df[ais_df["mmsi"].astype(str) == str(mmsi)].copy()
    if vessel.empty:
        return vessel
    vessel["timestamp"] = pd.to_datetime(vessel["timestamp"], errors="coerce", utc=True)
    vessel["lat"] = pd.to_numeric(vessel["lat"], errors="coerce")
    vessel["lon"] = pd.to_numeric(vessel["lon"], errors="coerce")
    vessel = vessel.dropna(subset=["timestamp", "lat", "lon"])
    return vessel.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")


def _distance_to_hull(df: pd.DataFrame, hull_lat: float, hull_lon: float):
    return haversine_km(hull_lat, hull_lon, df["lat"].to_numpy(), df["lon"].to_numpy())


def reconstruct_trajectory(
    ais_df: pd.DataFrame,
    mmsi: str,
    hull_lat: float,
    hull_lon: float,
    detection_time: datetime,
    window_hours: float = 6.0,
    vicinity_km: float = 2.0,
) -> VesselTrajectory:
    """Build an observed AIS track around a SAR event.

    ``vicinity_km`` describes an investigation geometry around the detected
    hull; it is not an attribution radius.
    """
    vessel = _prepare_vessel(ais_df, mmsi)
    if detection_time.tzinfo is None:
        event = pd.Timestamp(detection_time, tz="UTC")
    else:
        event = pd.Timestamp(detection_time).tz_convert("UTC")

    window = vessel[
        (vessel["timestamp"] >= event - pd.Timedelta(hours=window_hours))
        & (vessel["timestamp"] <= event + pd.Timedelta(hours=window_hours))
    ].copy()

    if window.empty:
        return VesselTrajectory(
            mmsi=str(mmsi), points=[], points_before=0, points_after=0,
            nearest_distance_km=None, closest_timestamp=None,
            start_distance_km=None, end_distance_km=None,
            path_min_distance_km=None, path_intersects_vicinity=False,
            approaches_vicinity=False, status="INSUFFICIENT_TRAJECTORY_DATA",
            reason="No observed AIS positions were available in the configured trajectory window.",
        )

    distances = _distance_to_hull(window, hull_lat, hull_lon)
    window["distance_to_hull_km"] = distances
    before = window[window["timestamp"] < event]
    after = window[window["timestamp"] > event]

    points = [
        TrackPoint(
            timestamp=row["timestamp"].isoformat().replace("+00:00", "Z"),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            distance_to_hull_km=round(float(row["distance_to_hull_km"]), 3),
        )
        for _, row in window.iterrows()
    ]

    nearest_idx = int(window["distance_to_hull_km"].idxmin())
    nearest_row = window.loc[nearest_idx]
    nearest = float(nearest_row["distance_to_hull_km"])

    if len(before) >= 1:
        start_distance = float(before.iloc[0]["distance_to_hull_km"])
        end_distance = float(before.iloc[-1]["distance_to_hull_km"])
    else:
        start_distance = float(window.iloc[0]["distance_to_hull_km"])
        end_distance = float(window.iloc[-1]["distance_to_hull_km"])

    # Use observed AIS points themselves for the vicinity test. We deliberately
    # do not interpolate a crossing between sparse points as if it were observed.
    intersects = bool((window["distance_to_hull_km"] <= vicinity_km).any())
    approaches = bool(end_distance + 0.25 < start_distance) and not intersects

    if intersects:
        status = "TRAJECTORY_INTERSECTS_SPILL_VICINITY"
        reason = (
            f"Observed AIS track contains at least one position within {vicinity_km:.1f} km "
            "of the SAR hull location."
        )
    elif approaches:
        status = "TRAJECTORY_APPROACHES_SPILL_VICINITY"
        reason = "Observed track endpoint is materially closer to the SAR hull than the track start."
    elif end_distance > start_distance + 0.25:
        status = "TRAJECTORY_PASSES_AWAY"
        reason = "Observed track endpoint is materially farther from the SAR hull than the track start."
    elif len(window) >= 2:
        status = "TRAJECTORY_OBSERVED_NO_CLEAR_APPROACH"
        reason = "Observed AIS track is available, but its endpoints do not show a clear approach or departure pattern."
    else:
        status = "INSUFFICIENT_TRAJECTORY_DATA"
        reason = "Only one observed AIS position is available, so trajectory direction cannot be established."

    return VesselTrajectory(
        mmsi=str(mmsi),
        points=points,
        points_before=len(before),
        points_after=len(after),
        nearest_distance_km=round(nearest, 3),
        closest_timestamp=nearest_row["timestamp"].isoformat().replace("+00:00", "Z"),
        start_distance_km=round(start_distance, 3),
        end_distance_km=round(end_distance, 3),
        path_min_distance_km=round(nearest, 3),
        path_intersects_vicinity=intersects,
        approaches_vicinity=approaches,
        status=status,
        reason=reason,
    )


def trajectory_to_dict(result: VesselTrajectory) -> dict:
    return {
        "mmsi": result.mmsi,
        "points": [
            {
                "timestamp": p.timestamp,
                "lat": p.lat,
                "lon": p.lon,
                "distance_to_hull_km": p.distance_to_hull_km,
            }
            for p in result.points
        ],
        "points_before": result.points_before,
        "points_after": result.points_after,
        "nearest_distance_km": result.nearest_distance_km,
        "closest_timestamp": result.closest_timestamp,
        "start_distance_km": result.start_distance_km,
        "end_distance_km": result.end_distance_km,
        "path_min_distance_km": result.path_min_distance_km,
        "path_intersects_vicinity": result.path_intersects_vicinity,
        "approaches_vicinity": result.approaches_vicinity,
        "status": result.status,
        "reason": result.reason,
        "responsibility_status": "NOT_ESTABLISHED",
    }
