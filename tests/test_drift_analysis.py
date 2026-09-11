from datetime import datetime, timezone

from main.drift_analysis import estimate_source_zone, drift_to_dict, enrich_incident_with_drift


def test_drift_backtracks_opposite_to_transport():
    result = estimate_source_zone(10.0, 80.0, "2026-06-21T12:00:00Z", [{"timestamp":"2026-06-21T11:00:00Z","current_u_mps":1.0,"current_v_mps":0.0,"wind_u_mps":0.0,"wind_v_mps":0.0}])
    assert result.status == "ESTIMATED"
    assert result.origin_lon < 80.0
    assert abs(result.origin_lat - 10.0) < 0.001
    assert result.uncertainty_km == 2.0


def test_windage_is_applied_to_effective_velocity():
    result = estimate_source_zone(10.0, 80.0, datetime(2026,6,21,12,tzinfo=timezone.utc), [{"timestamp":"2026-06-21T11:00:00Z","current_u_mps":0.0,"current_v_mps":0.0,"wind_u_mps":2.0,"wind_v_mps":0.0}], windage=0.05)
    assert result.status == "ESTIMATED"
    assert result.effective_u_mps == 0.1
    assert result.origin_lon < 80.0


def test_missing_environmental_data_is_explicitly_unavailable():
    result = estimate_source_zone(10.0,80.0,"2026-06-21T12:00:00Z",None)
    assert result.status == "NOT_AVAILABLE"
    assert result.origin_lat is None
    assert result.origin_lon is None


def test_invalid_environmental_rows_are_unavailable():
    result = estimate_source_zone(10.0,80.0,"2026-06-21T12:00:00Z",[{"timestamp":"bad","current_u_mps":"x"}])
    assert result.status == "NOT_AVAILABLE"


def test_incident_enrichment_keeps_drift_as_estimated_evidence():
    incident = {"detection":{"timestamp":"2026-06-21T12:00:00Z"},"spill":{"components":[{"geolocation":{"lat":10.0,"lon":80.0}}]}}
    enriched = enrich_incident_with_drift(incident,[{"timestamp":"2026-06-21T11:00:00Z","current_u_mps":1.0,"current_v_mps":0.0}])
    assert enriched["drift"]["status"] == "ESTIMATED"
    assert enriched["drift"]["uncertainty_km"] == 2.0
    assert enriched["environmental"]["status"] == "AVAILABLE"
    assert enriched["drift"]["origin_lon"] < 80.0


def test_drift_serializer_is_json_safe():
    result = estimate_source_zone(10.0,80.0,"2026-06-21T12:00:00Z",[])
    payload = drift_to_dict(result)
    assert payload["status"] == "NOT_AVAILABLE"
    assert isinstance(payload["steps"], list)
