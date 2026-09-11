"""Transparent multi-vessel ranking for IMW investigations.

Ranks observed AIS candidates for a SAR-detected hull. The score is an
investigation-priority score, not a probability of responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RankedCandidate:
    rank: int
    hull_id: int | None
    mmsi: str | None
    vessel_name: str | None
    priority_score: float
    priority: str
    evidence_confidence: str
    spatial_distance_km: float | None
    temporal_delta_minutes: float | None
    ais_coverage: str
    ais_gap: str
    history_continuity: str
    association_classification: str
    reasons: list[str]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _priority(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.50:
        return "MEDIUM"
    return "LOW"


def _gap_score(history: dict, candidate: dict) -> float | None:
    """Convert AIS-gap evidence into modest investigation-priority evidence."""
    gap = candidate.get("ais_gap") or candidate.get("gap_analysis") or history.get("gap_analysis")
    if not isinstance(gap, dict):
        status = history.get("ais_gap_status") or history.get("gap_status")
        if status is None:
            return None
        gap = {"status": status}

    status = str(gap.get("status") or "").upper()
    if status == "AIS_GAP_OBSERVED":
        return 0.65
    if status == "GAP_REQUIRES_COVERAGE_REVIEW":
        return 0.35
    if status == "AIS_CONTINUITY_OBSERVED":
        return 0.0
    if status in {"NO_COVERAGE_TO_ASSESS", "NO_OBSERVATIONS", "INSUFFICIENT_DATA"}:
        return None
    return None


def rank_candidates(candidates: list[dict]) -> list[RankedCandidate]:
    """Rank candidates without ever assigning responsibility."""
    ranked: list[RankedCandidate] = []
    for c in candidates:
        association = c.get("association") or {}
        history = c.get("vessel_history") or {}
        distance = c.get("distance_km")
        hours = c.get("time_diff_hours")
        spatial = max(0.0, 1.0 - float(distance) / 10.0) if distance is not None else None
        temporal = max(0.0, 1.0 - float(hours) / 2.0) if hours is not None else None
        continuity = history.get("evidence_strength")
        trajectory = (c.get("trajectory") or {}).get("trajectory_score")
        gap = _gap_score(history, c)

        # Fixed weights make an observed AIS gap additive evidence instead of
        # penalising a candidate merely because gap evidence was previously
        # absent. Missing evidence contributes zero; it is not treated as a
        # negative finding. AIS gaps remain capped at 12% of the total score.
        values = [
            (0.30, spatial),
            (0.18, temporal),
            (0.18, continuity),
            (0.22, trajectory),
            (0.12, gap),
        ]
        available = [(w, v) for w, v in values if v is not None]
        total_weight = sum(w for w, _ in available)
        score = sum(w * _clamp(v) for w, v in available)

        reasons = []
        if distance is not None:
            reasons.append(f"{distance:.2f} km from detected hull")
        if hours is not None:
            reasons.append(f"{hours * 60:.1f} min from SAR event")
        if history.get("status"):
            reasons.append(str(history["status"]))
        if trajectory is not None:
            reasons.append(f"trajectory evidence {float(trajectory):.2f}")

        gap_source = c.get("ais_gap") or c.get("gap_analysis") or history.get("gap_analysis")
        gap_status = gap_source.get("status") if isinstance(gap_source, dict) else None
        if gap_status:
            reasons.append(f"AIS gap evidence: {gap_status}")

        if not reasons:
            reasons.append("Insufficient observed evidence")

        confidence = "HIGH" if total_weight >= 0.75 else ("MEDIUM" if total_weight >= 0.50 else "LOW")
        ranked.append(RankedCandidate(
            rank=0,
            hull_id=c.get("hull_id"),
            mmsi=c.get("matched_mmsi"),
            vessel_name=c.get("matched_vessel_name"),
            priority_score=round(score, 3),
            priority=_priority(score),
            evidence_confidence=confidence,
            spatial_distance_km=round(float(distance), 3) if distance is not None else None,
            temporal_delta_minutes=round(float(hours) * 60.0, 2) if hours is not None else None,
            ais_coverage=c.get("coverage_status", "UNKNOWN"),
            ais_gap=gap_status or history.get("status", "NOT_ASSESSABLE"),
            history_continuity=history.get("status", "NOT_ASSESSABLE"),
            association_classification=association.get("classification", "UNRESOLVED"),
            reasons=reasons,
        ))

    ranked.sort(key=lambda x: x.priority_score, reverse=True)
    for index, item in enumerate(ranked, 1):
        item.rank = index
    return ranked


def ranked_to_dict(items: list[RankedCandidate]) -> list[dict]:
    return [
        {
            "rank": x.rank,
            "hull_id": x.hull_id,
            "mmsi": x.mmsi,
            "vessel_name": x.vessel_name,
            "priority_score": x.priority_score,
            "priority": x.priority,
            "evidence_confidence": x.evidence_confidence,
            "spatial_distance_km": x.spatial_distance_km,
            "temporal_delta_minutes": x.temporal_delta_minutes,
            "ais_coverage": x.ais_coverage,
            "ais_gap": x.ais_gap,
            "history_continuity": x.history_continuity,
            "association_classification": x.association_classification,
            "responsibility_status": "NOT_ESTABLISHED",
            "reasons": x.reasons,
        }
        for x in items
    ]
