from main.vessel_evidence import score_vessel_candidate


def test_candidate_score_is_explainable():
    result = score_vessel_candidate(
        mmsi="123",
        vessel_name="TEST VESSEL",
        distance_km=2,
        time_delta_minutes=5,
        before_count=4,
        after_count=3,
        gap_minutes=20,
    )
    assert result["classification"] == "STRONG_CANDIDATE"
    assert set(result["components"]) == {
        "proximity", "temporal", "ais_continuity", "ais_gap_signal"
    }
    assert "does not establish responsibility" in result["warning"]


def test_missing_position_and_time_remains_unresolved():
    result = score_vessel_candidate(
        mmsi="456",
        vessel_name=None,
        distance_km=None,
        time_delta_minutes=None,
        before_count=0,
        after_count=0,
    )
    assert result["classification"] == "UNRESOLVED"
    assert result["score"] == 0.0
