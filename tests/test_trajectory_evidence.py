from datetime import datetime

import pandas as pd

from main.trajectory_evidence import analyze_trajectory


def _df(rows):
    return pd.DataFrame(rows, columns=["mmsi", "timestamp", "lat", "lon", "heading"])


def test_trajectory_reports_pre_and_post_event_points():
    event = datetime(2026, 1, 1, 12, 0, 0)
    df = _df([
        ["123", "2026-01-01T10:00:00", 10.2, 80.0, 180],
        ["123", "2026-01-01T11:30:00", 10.05, 80.0, 180],
        ["123", "2026-01-01T12:30:00", 9.95, 80.0, 180],
        ["123", "2026-01-01T14:00:00", 9.8, 80.0, 180],
    ])
    result = analyze_trajectory(df, "123", 10.0, 80.0, event)
    assert result.points_before == 2
    assert result.points_after == 2
    assert result.nearest_before_km is not None
    assert result.trajectory_score > 0.5
    assert result.status == "TRAJECTORY_EVIDENCE_AVAILABLE"


def test_trajectory_without_pre_event_points_is_insufficient():
    event = datetime(2026, 1, 1, 12, 0, 0)
    df = _df([
        ["123", "2026-01-01T13:00:00", 10.1, 80.0, 180],
    ])
    result = analyze_trajectory(df, "123", 10.0, 80.0, event)
    assert result.points_before == 0
    assert result.status == "NO_PRE_EVENT_TRAJECTORY"
    assert result.trajectory_score == 0.0
