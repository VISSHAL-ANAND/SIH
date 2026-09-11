"""Phase 4K — deterministic, auditable IMW incident report builder."""
from __future__ import annotations
from datetime import datetime, timezone
import json


def build_incident_report(incident: dict, response_draft: dict | None = None) -> dict:
    draft = response_draft or {}
    return {
        "report_type": "IMW_MARINE_INCIDENT_REPORT",
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "incident_id": incident.get("incident_id"),
        "detection": incident.get("detection") or {},
        "geolocation": incident.get("geolocation") or {},
        "spill": incident.get("spill") or {},
        "ais": incident.get("ais") or {},
        "environmental": incident.get("environmental") or {"status": "NOT_AVAILABLE"},
        "candidates": incident.get("candidates") or [],
        "drift": incident.get("drift") or {},
        "rf": incident.get("rf") or {},
        "limitations": incident.get("limitations") or [],
        "response": {
            "status": draft.get("status", "NOT_PREPARED"),
            "urgency": draft.get("urgency", "REVIEW"),
            "operator_confirmation": draft.get("operator_confirmation", {"required": True, "confirmed": False}),
            "transmission": draft.get("transmission", {"status": "NOT_SENT"}),
        },
        "audit": {
            "source": "IMW_EVIDENCE_PACKAGE",
            "machine_generated": True,
            "legal_responsibility_established": False,
        },
    }


def report_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)
