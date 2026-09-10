from datetime import datetime, timedelta

import pandas as pd

from main.ais_candidates import find_ais_candidates


def test_returns_all_distinct_mmsi_candidates_in_window():
    event = datetime(2026, 9, 10, 12, 0, 0)
    frame = pd.DataFrame([
        {"mmsi": "111", "vessel_name": "A", "lat": 10.000, "lon": 72.000, "timestamp": event},
        {"mmsi": "222", "vessel_name": "B", "lat": 10.020, "lon": 72.000, "timestamp": event + timedelta(minutes=10)},
        {"mmsi": "111", "vessel_name": "A", "lat": 10.001, "lon": 72.001, "timestamp": event + timedelta(minutes=20)},
        {"mmsi": "999", "vessel_name": "OUTSIDE", "lat": 12.000, "lon": 72.000, "timestamp": event},
    ])
    candidates = find_ais_candidates(10.0, 72.0, event, frame, radius_km=10, time_hours=2)
    assert {c["mmsi"] for c in candidates} == {"111", "222"}
    assert candidates[0]["mmsi"] == "111"
    assert all(c["responsibility_status"] == "NOT_ESTABLISHED" for c in candidates)


def test_empty_ais_is_not_a_dark_vessel_claim():
    event = datetime(2026, 9, 10, 12, 0, 0)
    candidates = find_ais_candidates(10.0, 72.0, event, pd.DataFrame(), radius_km=10, time_hours=2)
    assert candidates == []
