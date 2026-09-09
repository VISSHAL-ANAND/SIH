from main.evidence_fusion import fuse_evidence, fusion_to_dict
from main.incident_response import build_response_draft
from main.incident_report import build_incident_report, report_json


def test_end_to_end_investigation_package():
    fusion = fusion_to_dict(fuse_evidence(0.92, 0.84, 0.70, 0.78, None))
    incident = {
        "incident_id": "IMW-E2E-001",
        "detection": {"timestamp": "2026-01-01T12:00:00Z"},
        "geolocation": {"hulls": [{"lat": 12.3001, "lon": 74.5002}]},
        "spill": {"count": 1, "classification": "LINEAR_TRAIL"},
        "ais": {"window_status": "AVAILABLE"},
        "candidates": [{
            "mmsi": "123456789",
            "vessel_name": "TEST VESSEL",
            "classification": fusion["classification"],
            "fusion": fusion,
        }],
        "drift": {"status": "NOT_AVAILABLE"},
        "rf": {"status": "NOT_AVAILABLE"},
        "limitations": fusion["limitations"],
    }

    draft = build_response_draft(incident, urgency="HIGH")
    report = build_incident_report(incident, draft)

    assert report["incident_id"] == "IMW-E2E-001"
    assert report["response"]["status"] == "DRAFT_REQUIRES_OPERATOR_CONFIRMATION"
    assert report["response"]["transmission"]["status"] == "NOT_SENT"
    assert report["audit"]["legal_responsibility_established"] is False
    assert report["candidates"][0]["fusion"]["classification"] == fusion["classification"]
    assert "IMW-E2E-001" in report_json(report)
