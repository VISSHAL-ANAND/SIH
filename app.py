"""
Indo Marine Watch (IMW) — Maritime Intelligence Backend
=======================================================
Government-grade FastAPI service for automated oil-spill SAR processing,
dark-vessel AIS/RF attribution, and operator-reviewed Coast Guard response.
"""

import sys
import time
import uuid
import hashlib
import hmac as hmac_mod
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
MAIN_DIR = BASE_DIR / "main"
TEMP_DIR = BASE_DIR / "temp"
STATIC_DIR = BASE_DIR / "static"
TEMP_DIR.mkdir(exist_ok=True)

if str(MAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from models import run_sar_segmentation, run_hull_detection, classify_slick_pca_shape
from physics import fetch_open_meteo_environment, simulate_backward_drift_trajectory
from sensor_fusion import correlate_hull_with_ais, haversine_km, MOCK_AIS_BROADCASTS
from main.imw_real_pipeline import run_real_pipeline

app = FastAPI(
    title="Indo Marine Watch (IMW)",
    description="Government Maritime Intelligence — Oil Spill Detection & Dark Vessel Attribution",
    version="4.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class AnalyzeIncidentRequest(BaseModel):
    scenario: str = Field(default="msc_elsa_3")
    hours_back: float = Field(default=6.0, ge=0.5, le=24.0)


class AnalyzeTrafficRequest(BaseModel):
    slick_lat: float
    slick_lon: float
    hull_lat: float
    hull_lon: float
    capture_time: Optional[str] = None


class PrepareResponseRequest(BaseModel):
    incident_id: str
    slick_centroid: List[float]
    spill_area_sq_m: float
    suspect_vessel: Dict[str, Any]
    threat_score: float
    evidence_summary: Optional[str] = None
    recipient: Optional[str] = None


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
        "operator_confirmation": {
            "required": True,
            "confirmed": False,
            "confirmed_by": None,
            "confirmed_at": None,
        },
        "transmission": {"status": "NOT_SENT", "sent_at": None},
        "notice": "Draft only. Verify evidence and recipient details before any official transmission.",
    }


@app.post("/api/analyze-incident")
async def analyze_incident(request: AnalyzeIncidentRequest) -> Dict[str, Any]:
    """Original single-call pipeline retained for backward compatibility."""
    t_start = time.perf_counter()
    slick_lat, slick_lon = 9.3764, 75.9758
    kerala_env_lat, kerala_env_lon = 9.3500, 76.0800
    sar_res = run_sar_segmentation(pixel_count=1000)
    hull_res = run_hull_detection(slick_lat=slick_lat, slick_lon=slick_lon)
    env_params = fetch_open_meteo_environment(lat=kerala_env_lat, lon=kerala_env_lon)
    drift_res = simulate_backward_drift_trajectory(
        slick_lat=slick_lat, slick_lon=slick_lon,
        hours_back=request.hours_back, env_params=env_params,
    )
    hull_lat, hull_lon = hull_res["coordinates"]
    fusion_res = correlate_hull_with_ais(hull_lat=hull_lat, hull_lon=hull_lon, tolerance_km=5.0)
    t_end = time.perf_counter()
    incident_id = f"INCIDENT-{request.scenario.upper().replace('_', '-')}-2026"
    return {
        "status": "success",
        "incident_id": incident_id,
        "pipeline_latency_ms": round((t_end - t_start) * 1000, 2),
        "target_vessel_coordinates": fusion_res["target_vessel_coordinates"],
        "slick_centroid": [slick_lat, slick_lon],
        "origin_coordinates": drift_res["origin_coordinates"],
        "drift_distance_km": drift_res["drift_distance_km"],
        "hours_back": request.hours_back,
        "spill_area_sq_m": sar_res["spill_area_sq_m"],
        "shape_classification": sar_res["shape_classification"],
        "sensor_fusion": {
            "ais_status": fusion_res["ais_status"],
            "is_dark_vessel": fusion_res["is_dark_vessel"],
            "rf_intercept_match": fusion_res["rf_intercept_match"],
            "rf_signature": fusion_res["rf_signature"],
            "threat_score": fusion_res["threat_score"],
            "attribution_reason": fusion_res["attribution_reason"],
        },
        "environment": env_params,
    }


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
