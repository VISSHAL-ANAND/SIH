"""
Indo Marine Watch (IMW) — FastAPI backend.

The API exposes the real-only SAR investigation pipeline and a reviewable
Coast Guard response draft. External authority transmission is never automatic.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from main.imw_real_pipeline import run_real_pipeline

app = FastAPI(title="Indo Marine Watch", version="4.1.0")
TEMP_DIR = Path("/tmp/imw")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class AnalyzeTrafficRequest(BaseModel):
    slick_lat: float
    slick_lon: float
    hull_lat: float
    hull_lon: float
    capture_time: Optional[str] = None


class PrepareResponseRequest(BaseModel):
    incident_id: str
    slick_centroid: list[Optional[float]]
    spill_area_sq_m: float = 0
    suspect_vessel: Dict[str, Any] = {}
    threat_score: float = 0
    evidence_summary: str = ""
    recipient: Optional[str] = None


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "IMW", "data_integrity": "REAL_ONLY"}


@app.post("/api/process-sar")
async def process_sar(
    file: UploadFile = File(...),
    center_lat: Optional[float] = Form(None),
    center_lon: Optional[float] = Form(None),
):
    """Canonical IMW SAR endpoint using the real-only pipeline."""
    t_start = time.perf_counter()
    safe_name = Path(file.filename or "upload.png").name
    file_path = TEMP_DIR / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    file_path.write_bytes(await file.read())
    try:
        result = run_real_pipeline(file_path, center_lat=center_lat, center_lon=center_lon, use_ais=True)
        result["pipeline_latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
        incident = result.get("incident") or {}
        # Keep the API envelope and canonical incident package on the same ID.
        incident_id = incident.get("incident_id") or f"IMW-{uuid.uuid4().hex[:8].upper()}-2026"
        result["incident_id"] = incident_id
        if isinstance(incident, dict):
            incident["incident_id"] = incident_id
        return {"status": "success", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"IMW real pipeline unavailable: {exc}")
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass


@app.post("/api/analyze-traffic")
async def analyze_traffic(request: AnalyzeTrafficRequest) -> Dict[str, Any]:
    """Return only real AIS correlation metadata; RF/track reconstruction is not fabricated."""
    from main.ais_matcher import AIS_CSV_PATH, load_ais_data, assess_ais_coverage, match_hull_to_ais

    ais_path = Path(AIS_CSV_PATH)
    if not ais_path.exists():
        return {
            "status": "success",
            "data_integrity": "REAL_ONLY",
            "ais_status": "NO_AIS_COVERAGE",
            "is_dark_vessel": False,
            "rf_intercept": {"status": "NOT_IMPLEMENTED"},
            "ais_track": [],
            "surrounding_traffic": [],
            "attribution_reason": "Configured AIS source is unavailable; no vessel attribution is made.",
        }

    ais_df = load_ais_data(str(ais_path))
    capture_time = (
        datetime.fromisoformat(request.capture_time.replace("Z", "+00:00")).replace(tzinfo=None)
        if request.capture_time
        else datetime.now(timezone.utc).replace(tzinfo=None)
    )
    coverage = assess_ais_coverage(ais_df, request.hull_lat, request.hull_lon, capture_time)
    match = match_hull_to_ais(request.hull_lat, request.hull_lon, capture_time, ais_df, hull_id=0)

    status = "AIS_MATCHED" if match.has_ais_match else coverage.status
    return {
        "status": "success",
        "data_integrity": "REAL_ONLY",
        "ais_status": status,
        "is_dark_vessel": bool(status == "AIS_GAP"),
        "suspect_vessel": {
            "name": match.matched_vessel_name or "UNIDENTIFIED",
            "mmsi": match.matched_mmsi or "---",
            "flag": "UNKNOWN",
            "type": "AIS-correlated vessel" if match.has_ais_match else "Unresolved SAR hull",
            "coordinates": [request.hull_lat, request.hull_lon],
            "threat_score": match.suspicion_score,
        },
        "rf_intercept": {"status": "NOT_IMPLEMENTED", "match": False, "signature": None, "lock_coordinates": None},
        "ais_track": [],
        "ais_blackout_point": None,
        "surrounding_traffic": [],
        "attribution_reason": coverage.reason if not match.has_ais_match else match.reason,
        "ais_match": {
            "matched_mmsi": match.matched_mmsi,
            "matched_vessel_name": match.matched_vessel_name,
            "distance_km": match.distance_km,
            "time_diff_hours": match.time_diff_hours,
            "suspicion_score": match.suspicion_score,
        },
        "coverage": {
            "status": coverage.status,
            "records_in_time_window": coverage.records_in_time_window,
            "nearby_records": coverage.nearby_records,
            "confidence": coverage.coverage_confidence,
            "reason": coverage.reason,
        },
    }


@app.post("/api/prepare-response")
async def prepare_response(request: PrepareResponseRequest) -> Dict[str, Any]:
    """Create a reviewable response draft; never transmit automatically."""
    timestamp = datetime.now(timezone.utc).isoformat()
    response_id = f"IMW-RESPONSE-{uuid.uuid4().hex[:8].upper()}"
    return {
        "status": "DRAFT_REQUIRES_OPERATOR_CONFIRMATION",
        "response_id": response_id,
        "timestamp": timestamp,
        "recipient": request.recipient or "Indian Coast Guard — operator to confirm",
        "incident_id": request.incident_id,
        "urgency": "HIGH" if request.threat_score >= 0.8 else "REVIEW",
        "payload_preview": {
            "incident_id": request.incident_id,
            "slick_centroid": request.slick_centroid,
            "spill_area_sq_m": request.spill_area_sq_m,
            "candidate_vessel": request.suspect_vessel,
            "threat_score": request.threat_score,
            "evidence_summary": request.evidence_summary,
        },
        "operator_confirmation": {"required": True, "confirmed": False},
        "transmission": "NOT_SENT",
        "notice": "Draft only. No external authority has been contacted.",
    }
