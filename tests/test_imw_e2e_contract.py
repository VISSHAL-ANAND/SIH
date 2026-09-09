"""Contract tests for the IMW SAR -> incident package boundary.

These tests intentionally use deterministic synthetic payloads; they do not
claim that synthetic data represents a real oil spill.
"""
from main.incident_package import CandidateVessel, build_incident_package
from main.rf_corroboration import RFObservation, corroborate_rf


def test_e2e_contract_contains_investigation_sections():
    rf = corroborate_rf(
        [RFObservation("2026-01-01T00:04:00Z", 10.001, 76.001, "TEST-RF", "rf-1")],
        10.0,
        76.0,
    )
    package = build_incident_package(
        incident_id="IMW-E2E-001",
        detection={"timestamp": "2026-01-01T00:00:00Z"},
        geolocation={"hulls": [{"lat": 10.0, "lon": 76.0}]},
        spill={"count": 1, "area_km2": 2.5},
        ais={"source_status": "AVAILABLE", "matches": [{"mmsi": "123"}]},
        rf=rf,
        candidates=[CandidateVessel("123", "TEST VESSEL", {"score": 0.85})],
    )
    data = package.__dict__

    required = {"incident_id", "detection", "geolocation", "spill", "ais", "rf", "candidates", "timeline"}
    assert required.issubset(data.keys())
    assert data["rf"]["status"] == "CORROBORATED"
    assert data["candidates"][0].mmsi == "123"


def test_missing_rf_does_not_break_e2e_contract():
    package = build_incident_package(
        incident_id="IMW-E2E-002",
        detection={"timestamp": "2026-01-01T00:00:00Z"},
        geolocation={"hulls": []},
        spill={},
        ais={"source_status": "NO_MATCH"},
    )
    assert package.rf["status"] == "NOT_AVAILABLE"
    assert package.timeline
