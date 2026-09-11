"""Explainable evidence fusion for IMW vessel investigations.

This module combines independent observed/modelled evidence into an
investigation-priority score. It is deliberately not a probability of legal
responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvidenceFusion:
    components: dict[str, float | None]
    available_weight: float
    score: float | None
    classification: str
    confidence: str
    evidence: list[str]
    limitations: list[str]
    responsibility_status: str = "NOT_ESTABLISHED"


# Fixed weights sum to 1.0. Missing evidence contributes zero to the score;
# it does not change the weight of evidence that is actually observed.
WEIGHTS = {
    "spatial": 0.25,
    "temporal": 0.15,
    "continuity": 0.15,
    "trajectory": 0.15,
    "drift": 0.30,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalise_spatial(distance_km: float | None) -> float | None:
    if distance_km is None:
        return None
    return max(0.0, 1.0 - float(distance_km) / 10.0)


def _normalise_temporal(hours: float | None) -> float | None:
    if hours is None:
        return None
    return max(0.0, 1.0 - float(hours) / 2.0)


def fuse_evidence(
    spatial: float | None,
    temporal: float | None,
    continuity: float | None,
    trajectory: float | None,
    drift: float | None,
) -> EvidenceFusion:
    values = {
        "spatial": spatial,
        "temporal": temporal,
        "continuity": continuity,
        "trajectory": trajectory,
        "drift": drift,
    }
    available_weight = sum(WEIGHTS[k] for k, v in values.items() if v is not None)
    if available_weight <= 0:
        return EvidenceFusion(
            values, 0.0, None, "UNRESOLVED", "INSUFFICIENT_DATA", [],
            ["No independent evidence is available."],
        )

    # Fixed denominator keeps the score calibrated across candidates. A
    # missing source is a limitation, not a negative observation.
    score = sum(
        WEIGHTS[k] * _clamp(v) for k, v in values.items() if v is not None
    )
    evidence = [f"{k}: {float(v):.3f}" for k, v in values.items() if v is not None]
    limitations = [f"{k} evidence unavailable" for k, v in values.items() if v is None]

    # Confidence measures evidence coverage separately from score strength.
    if available_weight >= 0.75:
        confidence = "HIGH"
    elif available_weight >= 0.50:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    if score >= 0.75 and available_weight >= 0.75:
        classification = "STRONG_CANDIDATE"
    elif score >= 0.50 and available_weight >= 0.50:
        classification = "POSSIBLE_CANDIDATE"
    elif score >= 0.25:
        classification = "WEAK_CANDIDATE"
    else:
        classification = "UNRESOLVED"

    return EvidenceFusion(
        values,
        round(available_weight, 3),
        round(score, 3),
        classification,
        confidence,
        evidence,
        limitations,
    )


def fuse_candidate(candidate: dict) -> EvidenceFusion:
    """Build fused evidence directly from a ranked AIS candidate payload."""
    distance = candidate.get("spatial_distance_km", candidate.get("distance_km"))
    temporal = candidate.get("temporal_delta_minutes")
    if temporal is None:
        hours = candidate.get("time_diff_hours")
        temporal = float(hours) * 60.0 if hours is not None else None
    temporal_hours = float(temporal) / 60.0 if temporal is not None else None

    history = candidate.get("vessel_history") or {}
    trajectory_data = candidate.get("trajectory") or {}
    drift_data = candidate.get("drift_evidence") or candidate.get("drift") or {}

    return fuse_evidence(
        _normalise_spatial(float(distance) if distance is not None else None),
        _normalise_temporal(temporal_hours),
        history.get("evidence_strength"),
        trajectory_data.get("trajectory_score"),
        drift_data.get("source_zone_score", drift_data.get("drift_score")),
    )


def fusion_to_dict(result: EvidenceFusion) -> dict:
    return {
        "components": result.components,
        "available_weight": result.available_weight,
        "score": result.score,
        "classification": result.classification,
        "confidence": result.confidence,
        "evidence": result.evidence,
        "limitations": result.limitations,
        "responsibility_status": result.responsibility_status,
    }
