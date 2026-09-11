from main.drift_candidate_evidence import enrich_candidates_with_drift


def test_estimated_drift_adds_source_zone_proximity():
    candidates = [{"mmsi": "123", "ais_lat": 10.05, "ais_lon": 80.05}]
    drift = {"status": "ESTIMATED", "origin_lat": 10.0, "origin_lon": 80.0}

    result = enrich_candidates_with_drift(candidates, drift)

    assert result[0]["drift_evidence_status"] == "ESTIMATED_SOURCE_ZONE_PROXIMITY"
    assert result[0]["drift_source_distance_km"] > 0
    assert 0 < result[0]["drift_source_score"] < 1
    assert result[0]["responsibility_status"] == "NOT_ESTABLISHED"


def test_unavailable_drift_does_not_create_false_evidence():
    candidates = [{"mmsi": "123", "ais_lat": 10.05, "ais_lon": 80.05}]

    result = enrich_candidates_with_drift(
        candidates, {"status": "NOT_AVAILABLE"}
    )

    assert result[0]["drift_source_distance_km"] is None
    assert result[0]["drift_source_score"] is None
    assert result[0]["drift_evidence_status"] == "NOT_AVAILABLE"


def test_missing_candidate_coordinates_remain_unavailable():
    candidates = [{"mmsi": "123"}]
    drift = {"status": "ESTIMATED", "origin_lat": 10.0, "origin_lon": 80.0}

    result = enrich_candidates_with_drift(candidates, drift)

    assert result[0]["drift_source_distance_km"] is None
    assert result[0]["drift_source_score"] is None
    assert result[0]["responsibility_status"] == "NOT_ESTABLISHED"


def test_multiple_candidates_are_all_evaluated():
    candidates = [
        {"mmsi": "near", "ais_lat": 10.0, "ais_lon": 80.01},
        {"mmsi": "far", "ais_lat": 10.0, "ais_lon": 80.10},
    ]
    drift = {"status": "ESTIMATED", "origin_lat": 10.0, "origin_lon": 80.0}

    result = enrich_candidates_with_drift(candidates, drift)

    assert result[0]["drift_source_distance_km"] < result[1]["drift_source_distance_km"]
    assert result[0]["drift_source_score"] > result[1]["drift_source_score"]
