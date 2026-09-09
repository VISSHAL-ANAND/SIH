"""Physics-light oil-spill drift backtracking for IMW.

This module estimates a *possible origin zone* from observed/assumed drift
vectors. It does not identify a spill source by itself. Current/wind inputs
must be supplied by an authorized environmental data source or explicitly
marked as assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians


@dataclass
class DriftStep:
    minutes_back: float
    latitude: float
    longitude: float


@dataclass
class DriftBacktrackResult:
    status: str
    origin_lat: float | None
    origin_lon: float | None
    uncertainty_km: float | None
    steps: list[dict]
    assumptions: list[str]
    reason: str


def backtrack_spill(
    spill_lat: float,
    spill_lon: float,
    detection_time_minutes: float,
    current_speed_mps: float = 0.0,
    current_direction_deg: float = 0.0,
    wind_speed_mps: float = 0.0,
    wind_direction_deg: float = 0.0,
    windage_factor: float = 0.03,
    step_minutes: float = 15.0,
) -> DriftBacktrackResult:
    """Backtrack a spill using supplied vectors.

    Direction is the direction the water/air mass travels *toward*.
    Backtracking therefore moves opposite those vectors.
    """
    if detection_time_minutes <= 0:
        return DriftBacktrackResult(
            status="NO_BACKTRACK_TIME",
            origin_lat=None, origin_lon=None, uncertainty_km=None,
            steps=[], assumptions=[],
            reason="A positive elapsed time since the assumed spill origin is required.",
        )

    steps = []
    lat, lon = float(spill_lat), float(spill_lon)
    remaining = float(detection_time_minutes)

    def vector(speed, direction):
        theta = radians(direction)
        return speed * cos(theta), speed * __import__("math").sin(theta)

    while remaining > 0:
        dt = min(step_minutes, remaining) * 60.0
        east, north = vector(current_speed_mps, current_direction_deg)
        we, wn = vector(wind_speed_mps * windage_factor, wind_direction_deg)
        east += we
        north += wn

        lat -= north * dt / 111_320.0
        lon -= east * dt / max(1.0, 111_320.0 * cos(radians(lat)))
        elapsed = detection_time_minutes - remaining + dt / 60.0
        steps.append({
            "minutes_back": round(elapsed, 1),
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
        })
        remaining -= dt / 60.0

    uncertainty = max(0.5, (current_speed_mps + wind_speed_mps * windage_factor) * 60.0 / 1000.0)

    return DriftBacktrackResult(
        status="ESTIMATED_ORIGIN_ZONE",
        origin_lat=round(lat, 6),
        origin_lon=round(lon, 6),
        uncertainty_km=round(uncertainty, 3),
        steps=steps,
        assumptions=[
            "Constant current vector over the backtrack interval.",
            "Constant wind vector over the backtrack interval.",
            f"Windage factor={windage_factor:.3f}.",
            "No shoreline interaction, spreading, evaporation, or weathering model is applied.",
        ],
        reason="Origin is an estimated drift-backtrack location, not proof of spill source.",
    )


def drift_to_dict(result: DriftBacktrackResult) -> dict:
    return {
        "status": result.status,
        "origin_lat": result.origin_lat,
        "origin_lon": result.origin_lon,
        "uncertainty_km": result.uncertainty_km,
        "steps": result.steps,
        "assumptions": result.assumptions,
        "reason": result.reason,
    }
