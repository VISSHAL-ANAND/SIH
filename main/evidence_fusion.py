"""IMW evidence fusion and explainable candidate ranking."""
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


# Evidence weights sum to 1.0.  Spatial and drift carry the strongest
# independent geographic signal; temporal, continuity, and trajectory provide
# complementary vessel-association evidence.
WEIGHTS = {
    "spatial": 0.25,
    "temporal": 0.15,
    "continuity": 0.15,
    "trajectory": 0.15,
    "drift": 0.30,
}


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
    total = sum(WEIGHTS[k] for k, v in values.items() if v is not None)
    if total <= 0:
        return EvidenceFusion(values, 0.0, None, "UNRESOLVED", "INSUFFICIENT_DATA", [],
                               ["No independent evidence is available."])

    score = sum(WEIGHTS[k] * max(0.0, min(1.0, float(v))) for k, v in values.items() if v is not None) / total
    evidence = [f"{k}: {float(v):.3f}" for k, v in values.items() if v is not None]
    limitations = [f"{k} evidence unavailable" for k, v in values.items() if v is None]

    if score >= 0.80 and total >= 0.75:
        classification, confidence = "STRONG_CANDIDATE", "HIGH"
    elif score >= 0.55 and total >= 0.50:
        classification, confidence = "POSSIBLE_CANDIDATE", "MEDIUM"
    elif score >= 0.35:
        classification, confidence = "WEAK_CANDIDATE", "LOW"
    else:
        classification, confidence = "UNRESOLVED", "LOW"

    return EvidenceFusion(values, round(total, 3), round(score, 3),
                          classification, confidence, evidence, limitations)


def fusion_to_dict(result: EvidenceFusion) -> dict:
    return {
        "components": result.components,
        "available_weight": result.available_weight,
        "score": result.score,
        "classification": result.classification,
        "confidence": result.confidence,
        "evidence": result.evidence,
        "limitations": result.limitations,
    }
