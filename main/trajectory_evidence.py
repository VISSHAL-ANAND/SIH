"""Trajectory evidence for IMW.

Uses observed AIS points to describe whether a vessel was moving toward/through
the SAR-detected hull. It is evidence for investigation only: it does not
claim causation or spill origin.
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
    movement_bearing_deg: float | None
    heading_alignment_score: float
    movement_alignment_score: float
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


def _prepare_vessel(ais_df: pd.DataFrame, mmsi: str) -> pd.DataFrame:
    required = {"mmsi", "timestamp", "lat", "lon"}
    if ais_df is None or ais_df.empty or not required.issubset(ais_df.columns):
        return pd.DataFrame(columns=list(required))
    vessel = ais_df[ais_df["mmsi"].astype(str) == str(mmsi)].copy()
    if vessel.empty:
        return vessel
    vessel["timestamp"] = pd.to_datetime(vessel["timestamp"], errors="coerce").dt.tz_localize(None)
    vessel["lat"] = pd.to_numeric(vessel["lat"], errors="coerce")
    vessel["lon"] = pd.to_numeric(vessel["lon"], errors="coerce")
    return vessel.dropna(subset=["timestamp", "lat", "lon"]).sort_values("timestamp")


def analyze_trajectory(
    ais_df: pd.DataFrame,
    mmsi: str,
    hull_lat: float,
    hull_lon: float,
    detection_time: datetime,
    window_hours: float = 6.0,
) -> TrajectoryEvidence:
    vessel = _prepare_vessel(ais_df, mmsi)
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
    movement_bearing = None
    proximity = 0.0
    heading_alignment = 0.0
    movement_alignment = 0.0

    if not before.empty:
        distances = haversine_km(
            hull_lat,
            hull_lon,
            before["lat"].to_numpy(),
            before["lon"].to_numpy(),
        )
        nearest_index = int(distances.argmin())
        nearest_before = float(distances[nearest_index])
        row = before.iloc[nearest_index]
        bearing = _bearing(float(row["lat"]), float(row["lon"]), hull_lat, hull_lon)

        if "heading" in row.index and pd.notna(row["heading"]):
            try:
                value = float(row["heading"])
                if 0.0 <= value <= 360.0:
                    heading = value
                    heading_alignment = max(0.0, 1.0 - _angle_delta(heading, bearing) / 180.0)
            except (TypeError, ValueError):
                pass

        # Prefer observed movement between the two latest pre-event AIS points.
        # This avoids treating a reported heading as proof of actual recent motion.
        if len(before) >= 2:
            previous = before.iloc[-2]
            latest = before.iloc[-1]
            movement_bearing = _bearing(
                float(previous["lat"]),
                float(previous["lon"]),
                float(latest["lat"]),
                float(latest["lon"]),
            )
            movement_alignment = max(
                0.0, 1.0 - _angle_delta(movement_bearing, bearing) / 180.0
            )

        proximity = max(0.0, 1.0 - nearest_before / 10.0)

    nearest_after = None
    if not after.empty:
        distances = haversine_km(
            hull_lat,
            hull_lon,
            after["lat"].to_numpy(),
            after["lon"].to_numpy(),
        )
        nearest_after = float(distances.min())

    directional_alignment = movement_alignment if len(before) >= 2 else heading_alignment
    score = 0.70 * proximity + 0.30 * directional_alignment

    if before.empty:
        status = "NO_PRE_EVENT_TRAJECTORY"
        reason = "No AIS track points were observed before the SAR event in the configured window."
    elif len(before) >= 2 and movement_alignment >= 0.70:
        status = "MOVEMENT_TOWARD_HULL_OBSERVED"
        reason = "Two or more observed pre-event AIS positions indicate recent movement direction toward the SAR hull."
    else:
        status = "TRAJECTORY_EVIDENCE_AVAILABLE"
        reason = "Observed pre-event AIS positions provide proximity and, when available, directional evidence toward the SAR hull."

    return TrajectoryEvidence(
        mmsi=str(mmsi),
        points_before=len(before),
        points_after=len(after),
        nearest_before_km=round(nearest_before, 3) if nearest_before is not None else None,
        nearest_after_km=round(nearest_after, 3) if nearest_after is not None else None,
        bearing_to_hull_deg=round(bearing, 2) if bearing is not None else None,
        observed_heading_deg=round(heading, 2) if heading is not None else None,
        movement_bearing_deg=round(movement_bearing, 2) if movement_bearing is not None else None,
        heading_alignment_score=round(heading_alignment, 3),
        movement_alignment_score=round(movement_alignment, 3),
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
        "movement_bearing_deg": result.movement_bearing_deg,
        "heading_alignment_score": result.heading_alignment_score,
        "movement_alignment_score": result.movement_alignment_score,
        "proximity_score": result.proximity_score,
        "trajectory_score": result.trajectory_score,
        "status": result.status,
        "reason": result.reason,
    }
