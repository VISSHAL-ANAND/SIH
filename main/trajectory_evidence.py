"""Trajectory evidence for IMW.

Uses observed AIS points to estimate whether a vessel was moving toward/through
the SAR-detected hull location. It is deliberately descriptive: it does not
claim causation or spill origin without an ocean-drift model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin

import pandas as pd

from .ais_matcher import haversine_km


@dataclass
class TrajectoryEvidence:
    mmsi: str
    points_before: int
    points_after: int
    nearest_before_km: float | None
    nearest_after_km: float | None
    bearing_to_hull_deg: float | None
    observed_heading_deg: float | None
    heading_alignment_score: float
    proximity_score: float
    trajectory_score: float
    status: str
    reason: str


def _bearing(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dl = radians(lon2 - lon1)
    y = sin(dl) * cos(p2)
    x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    return (atan2(y, x) * 180.0 / 3.141592653589793 + 360.0) % 360.0


def _angle_delta(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def analyze_trajectory(
    ais_df: pd.DataFrame,
    mmsi: str,
    hull_lat: float,
    hull_lon: float,
    detection_time: datetime,
    window_hours: float = 6.0,
) -> TrajectoryEvidence:
    vessel = ais_df[ais_df["mmsi"].astype(str) == str(mmsi)].copy()
    vessel["timestamp"] = pd.to_datetime(vessel["timestamp"], errors="coerce").dt.tz_localize(None)
    vessel = vessel.dropna(subset=["timestamp"]).sort_values("timestamp")
    detection_time = detection_time.replace(tzinfo=None)

    before = vessel[
        (vessel["timestamp"] < detection_time)
        & (vessel["timestamp"] >= detection_time - timedelta(hours=window_hours))
    ]
    after = vessel[
        (vessel["timestamp"] > detection_time)
        & (vessel["timestamp"] <= detection_time + timedelta(hours=window_hours))
    ]

    nearest_before = None
    bearing = None
    heading = None
    proximity = 0.0
    alignment = 0.0

    if not before.empty:
        d = haversine_km(hull_lat, hull_lon, before["lat"].to_numpy(), before["lon"].to_numpy())
        i = int(d.argmin())
        nearest_before = float(d[i])
        row = before.iloc[i]
        bearing = _bearing(float(row["lat"]), float(row["lon"]), hull_lat, hull_lon)
        if "heading" in row.index and pd.notna(row["heading"]) and 0 <= float(row["heading"]) <= 360:
            heading = float(row["heading"])
            alignment = max(0.0, 1.0 - _angle_delta(heading, bearing) / 180.0)
        proximity = max(0.0, 1.0 - nearest_before / 10.0)

    nearest_after = None
    if not after.empty:
        d = haversine_km(hull_lat, hull_lon, after["lat"].to_numpy(), after["lon"].to_numpy())
        nearest_after = float(d.min())

    score = 0.70 * proximity + 0.30 * alignment
    if before.empty:
        status = "NO_PRE_EVENT_TRAJECTORY"
        reason = "No AIS track points were observed before the SAR event in the configured window."
    else:
        status = "TRAJECTORY_EVIDENCE_AVAILABLE"
        reason = "Observed pre-event AIS positions provide proximity and, when heading exists, directional evidence toward the SAR hull."

    return TrajectoryEvidence(
        mmsi=str(mmsi),
        points_before=len(before),
        points_after=len(after),
        nearest_before_km=nearest_before,
        nearest_after_km=nearest_after,
        bearing_to_hull_deg=round(bearing, 2) if bearing is not None else None,
        observed_heading_deg=round(heading, 2) if heading is not None else None,
        heading_alignment_score=round(alignment, 3),
        proximity_score=round(proximity, 3),
        trajectory_score=round(score, 3),
        status=status,
        reason=reason,
    )


def trajectory_to_dict(result: TrajectoryEvidence) -> dict:
    return {
        "mmsi": result.mmsi,
        "points_before": result.points_before,
        "points_after": result.points_after,
        "nearest_before_km": result.nearest_before_km,
        "nearest_after_km": result.nearest_after_km,
        "bearing_to_hull_deg": result.bearing_to_hull_deg,
        "observed_heading_deg": result.observed_heading_deg,
        "heading_alignment_score": result.heading_alignment_score,
        "proximity_score": result.proximity_score,
        "trajectory_score": result.trajectory_score,
        "status": result.status,
        "reason": result.reason,
    }
