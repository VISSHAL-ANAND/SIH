"""Phase 4B: explicit IMW investigation state and decision gates."""


def build_investigation_state(incident: dict) -> dict:
    candidates = incident.get("candidates") or []
    ais = incident.get("ais") or {}
    rf = incident.get("rf") or {}
    drift = incident.get("drift") or {}

    dark_vessel_review = any(
        (c.get("association") or {}).get("classification") in {"UNRESOLVED", "WEAK_CANDIDATE"}
        for c in candidates if isinstance(c, dict)
    )

    return {
        "incident_id": incident.get("incident_id"),
        "stage": "EVIDENCE_REVIEW",
        "decision_gates": {
            "sar_detected": bool(incident.get("spill")),
            "geolocation_available": bool((incident.get("geolocation") or {}).get("hulls")),
            "ais_available": ais.get("source_status") not in {None, "NOT_REQUESTED", "UNAVAILABLE"},
            "dark_vessel_review": dark_vessel_review,
            "drift_available": drift.get("status") == "COMPLETED",
            "rf_corroborated": rf.get("status") == "CORROBORATED",
        },
        "operator_action_required": True,
        "provenance": "IMW_EVIDENCE_PACKAGE",
    }
