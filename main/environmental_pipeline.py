"""Adapter for attaching supplied environmental evidence to an IMW incident."""
from __future__ import annotations

from typing import Iterable

from .drift_analysis import enrich_incident_with_drift
from .imw_real_pipeline import run_real_pipeline


def run_pipeline_with_environment(
    image_path,
    center_lat=None,
    center_lon=None,
    use_ais=True,
    environmental_data: Iterable[dict] | None = None,
    *,
    windage: float = 0.03,
    uncertainty_km: float = 2.0,
):
    """Run the existing real pipeline and attach supplied drift evidence.

    This adapter keeps the default pipeline behavior unchanged: environmental
    evidence remains unavailable unless observations are explicitly supplied.
    """
    result = run_real_pipeline(
        image_path,
        center_lat=center_lat,
        center_lon=center_lon,
        use_ais=use_ais,
    )
    incident = result.get("incident") or {}
    result["incident"] = enrich_incident_with_drift(
        incident,
        environmental_data,
        windage=windage,
        uncertainty_km=uncertainty_km,
    )
    result["pipeline"] = dict(result.get("pipeline") or {})
    result["pipeline"]["environmental_evidence"] = (
        "AVAILABLE" if environmental_data else "NOT_AVAILABLE"
    )
    return result
