"""Phase 4E — explainable vessel-candidate evidence scoring.

Scores only supplied normalized AIS observations. It does not infer guilt.
"""
from __future__ import annotations


def score_vessel_candidate(
    *,
    mmsi: str,
    vessel_name: str | None,
    distance_km: float | None,
    time_delta_minutes: float | None,
    before_count: int,
    after_count: int,
    gap_minutes: float | None = None,
) -> dict:
    components = {}
    if distance_km is not None:
        components["proximity"] = max(0.0, min(1.0, 1.0 - distance_km / 20.0))
    else:
        components["proximity"] = None

    if time_delta_minutes is not None:
        components["temporal"] = max(0.0, min(1.0, 1.0 - time_delta_minutes / 60.0))
    else:
        components["temporal"] = None

    continuity = min(1.0, (before_count + after_count) / 6.0)
    components["ais_continuity"] = round(continuity, 3)

    gap_signal = None if gap_minutes is None else max(0.0, min(1.0, gap_minutes / 60.0))
    components["ais_gap_signal"] = round(gap_signal, 3) if gap_signal is not None else None

    available = [v for v in (components["proximity"], components["temporal"], components["ais_continuity"]) if v is not None]
    score = round(sum(available) / len(available), 3) if available else None

    if score is None:
        classification = "UNRESOLVED"
    elif score >= 0.75:
        classification = "STRONG_CANDIDATE"
    elif score >= 0.5:
        classification = "POSSIBLE"
    elif score >= 0.25:
        classification = "WEAK_CANDIDATE"
    else:
        classification = "UNRESOLVED"

    return {
        "mmsi": mmsi,
        "vessel_name": vessel_name,
        "score": score,
        "classification": classification,
        "components": components,
        "warning": "Candidate evidence is investigative only; it does not establish responsibility.",
    }
