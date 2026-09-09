"""Evidence-based spill-to-vessel association scoring for IMW."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp


@dataclass
class VesselAssociation:
    hull_id: int
    mmsi: str | None
    vessel_name: str | None
    distance_score: float
    time_score: float
    continuity_score: float
    overall_score: float
    classification: str
    evidence: list[str]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def score_vessel_association(
    hull_id: int,
    mmsi: str | None,
    vessel_name: str | None,
    distance_km: float | None,
    time_diff_hours: float | None,
    history: dict | None,
) -> VesselAssociation:
    """Score observed evidence; never converts missing data into positive evidence."""
    distance_score = 0.0 if distance_km is None else exp(-max(distance_km, 0.0) / 3.0)
    time_score = 0.0 if time_diff_hours is None else exp(-max(time_diff_hours, 0.0) / 1.0)
    continuity_score = float(history.get("evidence_strength", 0.0)) if history else 0.0

    # Weights emphasize direct SAR/AIS proximity while rewarding observed history.
    overall = (
        0.50 * distance_score
        + 0.25 * time_score
        + 0.25 * continuity_score
    )
    overall = _clamp(overall)

    evidence = []
    if distance_km is not None:
        evidence.append(f"AIS/SAR spatial separation: {distance_km:.2f} km")
    else:
        evidence.append("No spatial AIS match available")
    if time_diff_hours is not None:
        evidence.append(f"AIS/SAR temporal separation: {time_diff_hours:.2f} h")
    else:
        evidence.append("No temporal AIS match available")
    if history:
        evidence.append(f"AIS continuity status: {history.get('status', 'UNKNOWN')}")
    else:
        evidence.append("No vessel-history evidence available")

    if mmsi and overall >= 0.75:
        classification = "STRONG_CANDIDATE"
    elif mmsi and overall >= 0.45:
        classification = "POSSIBLE_CANDIDATE"
    elif mmsi:
        classification = "WEAK_CANDIDATE"
    else:
        classification = "UNRESOLVED"

    return VesselAssociation(
        hull_id=hull_id,
        mmsi=mmsi,
        vessel_name=vessel_name,
        distance_score=round(distance_score, 3),
        time_score=round(time_score, 3),
        continuity_score=round(continuity_score, 3),
        overall_score=round(overall, 3),
        classification=classification,
        evidence=evidence,
    )


def association_to_dict(result: VesselAssociation) -> dict:
    return {
        "hull_id": result.hull_id,
        "mmsi": result.mmsi,
        "vessel_name": result.vessel_name,
        "distance_score": result.distance_score,
        "time_score": result.time_score,
        "continuity_score": result.continuity_score,
        "overall_score": result.overall_score,
        "classification": result.classification,
        "evidence": result.evidence,
    }
