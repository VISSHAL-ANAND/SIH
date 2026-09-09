from main.incident_report import build_incident_report, report_json


def test_report_contains_evidence_and_audit_fields():
    incident = {
        "incident_id": "IMW-001",
        "detection": {"timestamp": "2026-01-01T12:00:00Z"},
        "geolocation": {"hulls": [{"lat": 12.3, "lon": 74.5}]},
        "spill": {"count": 1},
        "ais": {"source_status": "AVAILABLE"},
        "candidates": [{"mmsi": "123"}],
        "drift": {"status": "COMPLETED"},
        "rf": {"status": "NOT_AVAILABLE"},
        "limitations": ["RF unavailable"],
    }
    report = build_incident_report(incident)
    assert report["report_type"] == "IMW_MARINE_INCIDENT_REPORT"
    assert report["incident_id"] == "IMW-001"
    assert report["audit"]["machine_generated"] is True
    assert report["audit"]["legal_responsibility_established"] is False
    assert "RF unavailable" in report["limitations"]
    assert '"IMW-001"' in report_json(report)
