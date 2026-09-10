from datetime import datetime

from main.drift_analysis import estimate_source_zone


def test_drift_is_unavailable_without_environmental_observations():
    result = estimate_source_zone(10.0, 80.0, "2026-06-21T23:50:00Z", [])
    assert result.status == "NOT_AVAILABLE"
    assert result.origin_lat is None
    assert result.origin_lon is None


def test_drift_backtracks_using_supplied_current_vector():
    result = estimate_source_zone(
        10.0,
        80.0,
        datetime(2026, 6, 21, 23, 50),
        [{
            "timestamp": "2026-06-21T22:50:00Z",
            "current_u_mps": 1.0,
            "current_v_mps": 0.0,
            "wind_u_mps": 0.0,
            "wind_v_mps": 0.0,
        }],
        uncertainty_km=3.0,
    )
    assert result.status == "ESTIMATED"
    assert result.origin_lat == 10.0
    assert result.origin_lon < 80.0
    assert result.uncertainty_km == 3.0
    assert result.steps[0]["effective_u_mps"] == 1.0


def test_windage_is_applied_to_wind_components():
    result = estimate_source_zone(
        10.0,
        80.0,
        "2026-06-21T23:50:00Z",
        [{
            "timestamp": "2026-06-21T22:50:00Z",
            "current_u_mps": 0.0,
            "current_v_mps": 0.0,
            "wind_u_mps": 10.0,
            "wind_v_mps": 0.0,
        }],
        windage=0.1,
    )
    assert result.status == "ESTIMATED"
    assert result.effective_u_mps == 1.0
