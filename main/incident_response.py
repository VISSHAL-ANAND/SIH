"""Phase 4I — operator-controlled coastal response package.

Creates a reviewable response draft. It never transmits or claims that an
external authority was contacted.
"""
from __future__ import annotations


def build_response_draft(incident: dict, *, urgency: str = "REVIEW") -> dict:
    geo = incident.get("geolocation") or {}
    spill = incident.get("spill") or {}
    candidates = incident.get("candidates") or []
    limitations = incident.get("limitations") or []

    locations = geo.get("hulls") or []
    primary_location = locations[0] if locations else None

    return {
        "incident_id": incident.get("incident_id"),
        "status": "DRAFT_REQUIRES_OPERATOR_CONFIRMATION",
        "urgency": urgency if urgency in {"LOW", "REVIEW", "HIGH", "CRITICAL"} else "REVIEW",
        "subject": "Marine oil-spill incident — evidence review required",
        "summary": {
            "detection_time": (incident.get("detection") or {}).get("timestamp"),
            "spill_count": spill.get("count", 0),
            "primary_location": primary_location,
            "candidate_count": len(candidates),
        },
        "candidate_vessels": [
            {
                "mmsi": c.get("mmsi"),
                "vessel_name": c.get("vessel_name"),
                "classification": c.get("classification") or (c.get("association") or {}).get("classification"),
            }
            for c in candidates
        ],
        "limitations": limitations,
        "operator_confirmation": {
            "required": True,
            "confirmed": False,
            "confirmed_by": None,
            "confirmed_at": None,
        },
        "transmission": {
            "status": "NOT_SENT",
            "recipient": None,
        },
        "notice": "Draft only. Verify evidence and recipient details before any official transmission.",
    }
