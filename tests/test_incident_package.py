from main.incident_package import CandidateVessel, build_incident_package


def test_incident_package_preserves_rf_and_timeline():
    package = build_incident_package(
        incident_id="IMW-TEST-001",
        detection={"timestamp": "2026-01-01T00:00:00Z"},
        geolocation={"hulls": [{"lat": 10.0, "lon": 76.0}]},
        spill={"count": 1},
        ais={"source_status": "AVAILABLE"},
        rf={"status": "CORROBORATED", "score": 0.9},
        candidates=[CandidateVessel("123", "TEST VESSEL", {"score": 0.8})],
    )
    data = package.__dict__
    assert data["incident_id"] == "IMW-TEST-001"
    assert data["rf"]["status"] == "CORROBORATED"
    assert len(data["candidates"]) == 1
    assert data["timeline"][0].event_type == "SAR_DETECTION"


def test_incident_package_defaults_to_explicit_missing_rf():
    package = build_incident_package(
        incident_id="IMW-TEST-002",
        detection={},
        geolocation={},
        spill={},
        ais={},
    )
    assert package.rf["status"] == "NOT_AVAILABLE"
    assert "RF" in package.rf["reason"]
