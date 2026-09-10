"""Evidence-based spill-to-vessel association scoring for IMW.

This module scores observed SAR/AIS evidence. It deliberately does not infer
legal responsibility, causality, or intentional AIS shutdown from proximity.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp


@dataclass
class VesselAssociation:
    hull_id: int
    mmsi: str | None
    vessel_name: str | None
    spatial_distance_km: float | None
    temporal_delta_min: float | None
    distance_score: float
    time_score: float
    continuity_score: float
    overall_score: float
    classification: str
    ais_coverage_status: str
    ais_gap_status: str
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
    coverage_status: str | None = None,
) -> VesselAssociation:
    """Score observed evidence; never converts proximity into responsibility.

    ``overall_score`` is an evidence-confidence score, not a probability of
    guilt or responsibility. A vessel can only be classified as a candidate;
    this function never emits a responsible/culpable classification.
    """
    distance_score = 0.0 if distance_km is None else exp(-max(distance_km, 0.0) / 3.0)
    time_score = 0.0 if time_diff_hours is None else exp(-max(time_diff_hours, 0.0) / 1.0)
    continuity_score = float(history.get("evidence_strength", 0.0)) if history else 0.0
    overall = _clamp(0.50 * distance_score + 0.25 * time_score + 0.25 * continuity_score)

    temporal_delta_min = None if time_diff_hours is None else round(float(time_diff_hours) * 60.0, 2)
    coverage = coverage_status or "UNKNOWN"
    gap_status = "NOT_ESTABLISHED"
    if history:
        hstatus = history.get("status", "UNKNOWN")
        if hstatus == "POST_EVENT_GAP_UNRESOLVED" and coverage == "LOCAL_AIS_ACTIVITY":
            gap_status = "POTENTIAL_GAP_REQUIRES_REVIEW"
        elif hstatus == "CONTINUITY_OBSERVED":
            gap_status = "NO_GAP_OBSERVED"
        elif hstatus in {"NO_VESSEL_HISTORY", "NO_HISTORY_AROUND_EVENT"}:
            gap_status = "NOT_ASSESSABLE"

    evidence = []
    if distance_km is not None:
        evidence.append(f"SAR/AIS spatial separation: {distance_km:.2f} km")
    else:
        evidence.append("No spatial AIS match available")
    if temporal_delta_min is not None:
        evidence.append(f"SAR/AIS temporal separation: {temporal_delta_min:.2f} min")
    else:
        evidence.append("No temporal AIS match available")
    evidence.append(f"AIS coverage: {coverage}")
    evidence.append(f"AIS gap assessment: {gap_status}")
    if history:
        evidence.append(f"AIS continuity: {history.get('status', 'UNKNOWN')}")
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
        spatial_distance_km=None if distance_km is None else round(float(distance_km), 3),
        temporal_delta_min=temporal_delta_min,
        distance_score=round(distance_score, 3),
        time_score=round(time_score, 3),
        continuity_score=round(continuity_score, 3),
        overall_score=round(overall, 3),
        classification=classification,
        ais_coverage_status=coverage,
        ais_gap_status=gap_status,
        evidence=evidence,
    )


def association_to_dict(result: VesselAssociation) -> dict:
    return {
        "hull_id": result.hull_id,
        "mmsi": result.mmsi,
        "vessel_name": result.vessel_name,
        "spatial_distance_km": result.spatial_distance_km,
        "temporal_delta_min": result.temporal_delta_min,
        "distance_score": result.distance_score,
        "time_score": result.time_score,
        "continuity_score": result.continuity_score,
        "overall_score": result.overall_score,
        "evidence_confidence": result.overall_score,
        "classification": result.classification,
        "ais_coverage_status": result.ais_coverage_status,
        "ais_gap_status": result.ais_gap_status,
        "responsibility_status": "NOT_ESTABLISHED",
        "evidence": result.evidence,
    }
