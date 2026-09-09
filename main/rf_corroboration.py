"""RF corroboration primitives for IMW.

This module only scores supplied RF observations. It never invents RF data.
""" 
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass
class RFObservation:
    timestamp: str
    lat: float
    lon: float
    source: str
    signal_id: str | None = None


def distance_score(rf_lat: float, rf_lon: float, target_lat: float, target_lon: float, tolerance_km: float = 10.0) -> float:
    dlat = (rf_lat - target_lat) * 111.0
    dlon = (rf_lon - target_lon) * 111.0
    distance_km = sqrt(dlat * dlat + dlon * dlon)
    return max(0.0, min(1.0, 1.0 - distance_km / tolerance_km))


def corroborate_rf(observations: list[RFObservation], target_lat: float, target_lon: float) -> dict:
    if not observations:
        return {
            "status": "NOT_AVAILABLE",
            "matched": False,
            "score": None,
            "observations": [],
            "limitation": "No RF observations were supplied.",
        }

    best = max(observations, key=lambda o: distance_score(o.lat, o.lon, target_lat, target_lon))
    score = distance_score(best.lat, best.lon, target_lat, target_lon)
    return {
        "status": "CORROBORATED" if score >= 0.5 else "AVAILABLE_NO_CORROBORATION",
        "matched": score >= 0.5,
        "score": round(score, 3),
        "observations": [o.__dict__ for o in observations],
        "best_observation": best.__dict__,
    }
