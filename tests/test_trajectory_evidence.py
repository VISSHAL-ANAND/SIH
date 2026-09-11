"""Regression tests for AIS trajectory evidence."""
from datetime import datetime

import pandas as pd

from main.trajectory_evidence import analyze_trajectory, trajectory_to_dict


EVENT = datetime(2026, 1, 1, 12, 0)


def test_observed_movement_toward_hull_is_reported():
    df = pd.DataFrame([
        {"mmsi": "123", "timestamp": "2026-01-01 11:40", "lat": 9.98, "lon": 76.0, "heading": 0},
        {"mmsi": "123", "timestamp": "2026-01-01 11:50", "lat": 9.99, "lon": 76.0, "heading": 0},
        {"mmsi": "123", "timestamp": "2026-01-01 12:10", "lat": 10.01, "lon": 76.0, "heading": 0},
    ])
    result = analyze_trajectory(df, "123", 10.0, 76.0, EVENT)
    assert result.status == "MOVEMENT_TOWARD_HULL_OBSERVED"
    assert result.points_before == 2
    assert result.movement_bearing_deg is not None
    assert result.movement_alignment_score >= 0.99
    assert result.trajectory_score > 0.7


def test_heading_can_provide_directional_evidence_when_only_one_pre_event_point_exists():
    df = pd.DataFrame([
        {"mmsi": "123", "timestamp": "2026-01-01 11:50", "lat": 9.99, "lon": 76.0, "heading": 0},
    ])
    result = analyze_trajectory(df, "123", 10.0, 76.0, EVENT)
    assert result.status == "TRAJECTORY_EVIDENCE_AVAILABLE"
    assert result.movement_bearing_deg is None
    assert result.observed_heading_deg == 0.0
    assert result.heading_alignment_score >= 0.99


def test_invalid_or_missing_ais_is_explicitly_unavailable():
    result = analyze_trajectory(pd.DataFrame(), "123", 10.0, 76.0, EVENT)
    assert result.status == "NO_PRE_EVENT_TRAJECTORY"
    assert result.points_before == 0
    assert result.trajectory_score == 0.0


def test_serialized_evidence_contains_movement_fields():
    df = pd.DataFrame([
        {"mmsi": "123", "timestamp": "2026-01-01 11:50", "lat": 9.99, "lon": 76.0},
        {"mmsi": "123", "timestamp": "2026-01-01 11:55", "lat": 9.995, "lon": 76.0},
    ])
    payload = trajectory_to_dict(analyze_trajectory(df, "123", 10.0, 76.0, EVENT))
    assert "movement_bearing_deg" in payload
    assert "movement_alignment_score" in payload
    assert "trajectory_score" in payload
