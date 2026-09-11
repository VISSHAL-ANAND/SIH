from datetime import datetime, timezone

import pandas as pd

from main.vessel_trajectory import reconstruct_trajectory


EVENT = datetime(2026, 6, 21, 23, 50, tzinfo=timezone.utc)


def frame(rows):
    return pd.DataFrame(rows)


def test_trajectory_intersects_spill_vicinity():
    ais = frame([
        {"mmsi": "1001", "timestamp": "2026-06-21T20:00:00Z", "lat": 19.00, "lon": 92.00},
        {"mmsi": "1001", "timestamp": "2026-06-21T22:00:00Z", "lat": 19.10, "lon": 92.00},
        {"mmsi": "1001", "timestamp": "2026-06-21T23:40:00Z", "lat": 19.20, "lon": 92.00},
        {"mmsi": "1001", "timestamp": "2026-06-22T00:20:00Z", "lat": 19.30, "lon": 92.00},
    ])
    result = reconstruct_trajectory(ais, "1001", 19.20, 92.00, EVENT, vicinity_km=2.0)
    assert result.status == "TRAJECTORY_INTERSECTS_SPILL_VICINITY"
    assert result.path_intersects_vicinity is True
    assert result.points_before == 3
    assert result.points_after == 1


def test_trajectory_approaches_spill_vicinity_without_claiming_intersection():
    ais = frame([
        {"mmsi": "1002", "timestamp": "2026-06-21T19:00:00Z", "lat": 18.90, "lon": 92.00},
        {"mmsi": "1002", "timestamp": "2026-06-21T22:00:00Z", "lat": 19.00, "lon": 92.00},
        {"mmsi": "1002", "timestamp": "2026-06-21T23:40:00Z", "lat": 19.10, "lon": 92.00},
    ])
    result = reconstruct_trajectory(ais, "1002", 19.20, 92.00, EVENT, vicinity_km=2.0)
    assert result.status == "TRAJECTORY_APPROACHES_SPILL_VICINITY"
    assert result.approaches_vicinity is True
    assert result.path_intersects_vicinity is False
    assert result.responsibility_status == "NOT_ESTABLISHED"


def test_trajectory_passes_away():
    ais = frame([
        {"mmsi": "1003", "timestamp": "2026-06-21T19:00:00Z", "lat": 19.10, "lon": 92.00},
        {"mmsi": "1003", "timestamp": "2026-06-21T22:00:00Z", "lat": 19.00, "lon": 92.00},
        {"mmsi": "1003", "timestamp": "2026-06-21T23:40:00Z", "lat": 18.85, "lon": 92.00},
    ])
    result = reconstruct_trajectory(ais, "1003", 19.20, 92.00, EVENT)
    assert result.status == "TRAJECTORY_PASSES_AWAY"


def test_missing_track_is_insufficient():
    ais = frame([
        {"mmsi": "2000", "timestamp": "2026-06-20T19:00:00Z", "lat": 19.0, "lon": 92.0},
    ])
    result = reconstruct_trajectory(ais, "1004", 19.20, 92.00, EVENT)
    assert result.status == "INSUFFICIENT_TRAJECTORY_DATA"
    assert result.points == []


def test_sparse_single_point_is_insufficient():
    ais = frame([
        {"mmsi": "1005", "timestamp": "2026-06-21T23:40:00Z", "lat": 19.10, "lon": 92.00},
    ])
    result = reconstruct_trajectory(ais, "1005", 19.20, 92.00, EVENT)
    assert result.status == "INSUFFICIENT_TRAJECTORY_DATA"
    assert result.points_before == 1
