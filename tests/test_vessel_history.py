"""Tests for IMW AIS vessel-history analysis."""
from datetime import datetime

import pandas as pd

from main.vessel_history import analyze_vessel_history


def test_history_reports_continuity():
    df = pd.DataFrame([
        {"mmsi": "123", "timestamp": pd.Timestamp("2026-01-01 11:50"), "lat": 10.0, "lon": 76.0, "vessel_name": "TEST"},
        {"mmsi": "123", "timestamp": pd.Timestamp("2026-01-01 12:10"), "lat": 10.01, "lon": 76.01, "vessel_name": "TEST"},
    ])
    result = analyze_vessel_history(df, "123", 10.0, 76.0, datetime(2026, 1, 1, 12, 0))
    assert result.status == "CONTINUITY_OBSERVED"
    assert result.broadcasts_before == 1
    assert result.broadcasts_after == 1


def test_history_does_not_claim_shutdown_without_post_event_data():
    df = pd.DataFrame([
        {"mmsi": "123", "timestamp": pd.Timestamp("2026-01-01 11:50"), "lat": 10.0, "lon": 76.0, "vessel_name": "TEST"},
    ])
    result = analyze_vessel_history(df, "123", 10.0, 76.0, datetime(2026, 1, 1, 12, 0))
    assert result.status == "POST_EVENT_GAP_UNRESOLVED"
    assert result.evidence_strength < 0.5
