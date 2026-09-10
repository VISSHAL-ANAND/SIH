from main.incident_response import build_response_draft
from main.incident_report import build_incident_report


def _incident():
    return {
        "incident_id": "IMW-PHASE5-READY-001",
        "detection": {"timestamp": "2026-09-10T00:00:00Z", "source": "SAR"},
        "geolocation": {"hulls": [{"lat": 10.0, "lon": 72.0}]},
        "spill": {"count": 1, "area_sq_m": 1500},
        "ais": {"source_status": "AVAILABLE"},
        "environmental": {"status": "NOT_AVAILABLE"},
        "drift": {"status": "NOT_AVAILABLE"},
        "rf": {"status": "NOT_IMPLEMENTED"},
        "candidates": [{
            "mmsi": "123456789",
            "vessel_name": "TEST VESSEL",
            "classification": "UNRESOLVED",
            "association": {"classification": "UNRESOLVED"},
            "evidence": {"spatial": 0.9, "temporal": 0.8},
        }],
        "limitations": ["RF provider is not connected."],
    }


def test_report_preserves_evidence_integrity_states():
    incident = _incident()
    draft = build_response_draft(incident)
    report = build_incident_report(incident, draft)

    assert report["incident_id"] == incident["incident_id"]
    assert report["rf"]["status"] == "NOT_IMPLEMENTED"
    assert report["environmental"]["status"] == "NOT_AVAILABLE"
    assert report["response"]["status"] == "DRAFT_REQUIRES_OPERATOR_CONFIRMATION"
    assert report["response"]["transmission"]["status"] == "NOT_SENT"
    assert report["audit"]["machine_generated"] is True
    assert report["audit"]["legal_responsibility_established"] is False


def test_response_draft_never_marks_operator_as_confirmed():
    draft = build_response_draft(_incident())
    assert draft["operator_confirmation"]["required"] is True
    assert draft["operator_confirmation"]["confirmed"] is False
    assert draft["transmission"]["status"] == "NOT_SENT"
