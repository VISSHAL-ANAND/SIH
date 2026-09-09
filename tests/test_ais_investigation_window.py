from main.ais_investigation_window import build_ais_window, summarize_ais_window


def test_window_is_symmetric_around_detection():
    w = build_ais_window("2026-01-01T12:00:00Z", 30, 30)
    assert w["before"]["start"] == "2026-01-01T11:30:00+00:00"
    assert w["before"]["end"] == "2026-01-01T12:00:00+00:00"
    assert w["after"]["end"] == "2026-01-01T12:30:00+00:00"


def test_observations_are_split_before_and_after_detection():
    observations = [
        {"timestamp": "2026-01-01T11:45:00Z", "mmsi": "1"},
        {"timestamp": "2026-01-01T12:10:00Z", "mmsi": "1"},
    ]
    result = summarize_ais_window(observations, "2026-01-01T12:00:00Z")
    assert result["before_count"] == 1
    assert result["after_count"] == 1
    assert "not evidence of intentional shutdown" in result["interpretation"]


def test_empty_provider_data_is_not_called_dark_vessel():
    result = summarize_ais_window([], "2026-01-01T12:00:00Z")
    assert result["coverage_status"] == "NO_OBSERVATIONS"
    assert "not evidence" in result["interpretation"]
