from main.rf_corroboration import RFObservation, corroborate_rf


def test_no_rf_is_explicitly_unavailable():
    result = corroborate_rf([], 10.0, 76.0)
    assert result["status"] == "NOT_AVAILABLE"
    assert result["matched"] is False
    assert result["score"] is None


def test_nearby_rf_observation_corroborates():
    observations = [RFObservation("2026-01-01T00:00:00Z", 10.001, 76.001, "TEST")]
    result = corroborate_rf(observations, 10.0, 76.0)
    assert result["matched"] is True
    assert result["status"] == "CORROBORATED"
    assert result["score"] >= 0.5


def test_distant_rf_observation_does_not_corroborate():
    observations = [RFObservation("2026-01-01T00:00:00Z", 11.0, 77.0, "TEST")]
    result = corroborate_rf(observations, 10.0, 76.0)
    assert result["matched"] is False
    assert result["status"] == "AVAILABLE_NO_CORROBORATION"
