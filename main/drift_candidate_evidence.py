"""Connect estimated drift source zones to AIS investigation candidates.

This module adds source-zone proximity as evidence. It never establishes
vessel responsibility; the result is an investigation-priority signal only.
"""
from __future__ import annotations

from typing import Any

from .ais_matcher import haversine_km


def enrich_candidates_with_drift(
    candidates: list[dict[str, Any]],
    drift: dict[str, Any] | None,
    *,
    max_distance_km: float = 20.0,
) -> list[dict[str, Any]]:
    """Attach distance-to-drift-origin evidence to every candidate.

    Candidates without valid AIS coordinates or an estimated drift origin are
    left explicitly unavailable. No candidate is promoted solely by this step.
    """
    source = drift or {}
    origin_lat = source.get("origin_lat")
    origin_lon = source.get("origin_lon")
    if str(source.get("status") or "").upper() != "ESTIMATED":
        origin_lat = origin_lon = None

    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        item["drift_source_distance_km"] = None
        item["drift_source_score"] = None
        item["drift_evidence_status"] = "NOT_AVAILABLE"

        try:
            if origin_lat is None or origin_lon is None:
                raise ValueError
            lat = float(candidate.get("ais_lat"))
            lon = float(candidate.get("ais_lon"))
            distance = float(haversine_km(origin_lat, origin_lon, lat, lon))
            item["drift_source_distance_km"] = round(distance, 3)
            item["drift_source_score"] = round(
                max(0.0, 1.0 - distance / float(max_distance_km)), 3
            )
            item["drift_evidence_status"] = "ESTIMATED_SOURCE_ZONE_PROXIMITY"
        except (TypeError, ValueError):
            pass

        # Preserve the explicit non-attribution contract on every candidate.
        item["responsibility_status"] = "NOT_ESTABLISHED"
        enriched.append(item)

    return enriched
