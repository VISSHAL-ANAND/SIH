"""Transparent environmental drift backtracking for IMW.

This module estimates a *source zone*, not an exact discharge point. It only
runs when real/externally supplied current and/or wind observations are passed
in by the caller. Missing observations remain explicitly unavailable.

Velocity convention: ``current_u_mps``/``current_v_mps`` and
``wind_u_mps``/``wind_v_mps`` are eastward/northward components in m/s.
The wind contribution is scaled by ``windage`` before backtracking.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import cos, radians
from typing import Iterable

EARTH_RADIUS_M = 6_371_000.0


@dataclass
class DriftResult:
    status: str
    origin_lat: float | None
    origin_lon: float | None
    uncertainty_km: float | None
    elapsed_hours: float | None
    effective_u_mps: float | None
    effective_v_mps: float | None
    steps: list[dict]
    assumptions: list[str]
    reason: str


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _observation_velocity(observation: dict, windage: float) -> tuple[float, float]:
    cu = float(observation.get("current_u_mps", 0.0) or 0.0)
    cv = float(observation.get("current_v_mps", 0.0) or 0.0)
    wu = float(observation.get("wind_u_mps", 0.0) or 0.0)
    wv = float(observation.get("wind_v_mps", 0.0) or 0.0)
    return cu + windage * wu, cv + windage * wv


def _backtrack(lat: float, lon: float, u_mps: float, v_mps: float, seconds: float) -> tuple[float, float]:
    """Move a surface parcel backwards for ``seconds`` using a local tangent plane."""
    lat_scale = EARTH_RADIUS_M
    lon_scale = EARTH_RADIUS_M * max(cos(radians(lat)), 1e-6)
    return (
        lat - (v_mps * seconds / lat_scale) * 180.0 / 3.141592653589793,
        lon - (u_mps * seconds / lon_scale) * 180.0 / 3.141592653589793,
    )


def estimate_source_zone(
    spill_lat: float | None,
    spill_lon: float | None,
    detection_time: str | datetime | None,
    observations: Iterable[dict] | None,
    *,
    windage: float = 0.03,
    uncertainty_km: float = 2.0,
) -> DriftResult:
    """Backtrack from a SAR spill location using supplied environmental data.

    Observations are expected to contain a timestamp and velocity components.
    The observation nearest to the detection time is used. This intentionally
    favors a simple auditable model over an unsupported high-fidelity claim.
    """
    if spill_lat is None or spill_lon is None or detection_time is None:
        return DriftResult(
            status="NOT_AVAILABLE", origin_lat=None, origin_lon=None,
            uncertainty_km=None, elapsed_hours=None, effective_u_mps=None,
            effective_v_mps=None, steps=[], assumptions=[],
            reason="A georeferenced spill location and SAR detection time are required.",
        )

    rows = list(observations or [])
    if not rows:
        return DriftResult(
            status="NOT_AVAILABLE", origin_lat=None, origin_lon=None,
            uncertainty_km=None, elapsed_hours=None, effective_u_mps=None,
            effective_v_mps=None, steps=[], assumptions=[],
            reason="No current or wind observations were supplied.",
        )

    target = _parse_time(detection_time)
    usable = []
    for row in rows:
        try:
            ts = _parse_time(row["timestamp"])
            u, v = _observation_velocity(row, windage)
        except (KeyError, TypeError, ValueError):
            continue
        usable.append((abs((ts - target).total_seconds()), ts, u, v, row))

    if not usable:
        return DriftResult(
            status="NOT_AVAILABLE", origin_lat=None, origin_lon=None,
            uncertainty_km=None, elapsed_hours=None, effective_u_mps=None,
            effective_v_mps=None, steps=[], assumptions=[],
            reason="Supplied environmental observations could not be parsed into timestamped velocity vectors.",
        )

    _, ts, u, v, source_row = min(usable, key=lambda item: item[0])
    elapsed_hours = abs((target - ts).total_seconds()) / 3600.0
    origin_lat, origin_lon = _backtrack(float(spill_lat), float(spill_lon), u, v, elapsed_hours * 3600.0)
    assumptions = [
        "Surface transport is approximated by a constant local velocity vector.",
        f"Windage factor applied to supplied wind vector: {windage:.3f}.",
        f"Source-zone uncertainty is reported as {uncertainty_km:.1f} km and is not a legal attribution radius.",
        "The estimate does not model tides, wave-driven transport, diffusion, shoreline interaction, or changing currents between observations.",
    ]
    steps = [{
        "observation_timestamp": ts.isoformat() + "Z",
        "hours_from_detection": round((ts - target).total_seconds() / 3600.0, 3),
        "current_u_mps": float(source_row.get("current_u_mps", 0.0) or 0.0),
        "current_v_mps": float(source_row.get("current_v_mps", 0.0) or 0.0),
        "wind_u_mps": float(source_row.get("wind_u_mps", 0.0) or 0.0),
        "wind_v_mps": float(source_row.get("wind_v_mps", 0.0) or 0.0),
        "effective_u_mps": round(u, 5),
        "effective_v_mps": round(v, 5),
    }]
    return DriftResult(
        status="ESTIMATED",
        origin_lat=round(origin_lat, 6),
        origin_lon=round(origin_lon, 6),
        uncertainty_km=float(uncertainty_km),
        elapsed_hours=round(elapsed_hours, 3),
        effective_u_mps=round(u, 5), effective_v_mps=round(v, 5),
        steps=steps, assumptions=assumptions,
        reason="Estimated source zone from the nearest supplied environmental observation; operator review required.",
    )


def drift_to_dict(result: DriftResult) -> dict:
    return {
        "status": result.status,
        "origin_lat": result.origin_lat,
        "origin_lon": result.origin_lon,
        "uncertainty_km": result.uncertainty_km,
        "elapsed_hours": result.elapsed_hours,
        "effective_u_mps": result.effective_u_mps,
        "effective_v_mps": result.effective_v_mps,
        "steps": result.steps,
        "assumptions": result.assumptions,
        "reason": result.reason,
    }
