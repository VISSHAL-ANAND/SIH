"""Regression tests for coverage-aware AIS gap analysis."""
from datetime import datetime

import pandas as pd

from main.ais_gap_analysis import analyze_ais_gaps, gap_analysis_to_dict


def _df(rows):
    return pd.DataFrame(rows)


def test_confirmed_coverage_reports_significant_gap():
    df = _df([
        {"mmsi": "111", "timestamp": "2026-01-01 11:40", "lat": 10.0, "lon": 76.0},
        {"mmsi": "111", "timestamp": "2026-01-01 12:50", "lat": 10.1, "lon": 76.1},
    ])
    result = analyze_ais_gaps(
        df, "111", datetime(2026, 1, 1, 12, 0),
        expected_interval_minutes=15, coverage_available=True,
    )
    assert result.status == "AIS_GAP_OBSERVED"
    assert result.coverage_status == "COVERAGE_CONFIRMED"
    assert result.evidence_strength > 0


def test_unknown_coverage_requires_review_instead_of_dark_vessel_claim():
    df = _df([
        {"mmsi": "222", "timestamp": "2026-01-01 11:40", "lat": 10.0, "lon": 76.0},
        {"mmsi": "222", "timestamp": "2026-01-01 12:50", "lat": 10.1, "lon": 76.1},
    ])
    result = analyze_ais_gaps(
        df, "222", datetime(2026, 1, 1, 12, 0),
        expected_interval_minutes=15,
    )
    assert result.status == "GAP_REQUIRES_COVERAGE_REVIEW"
    assert "intentional shutdown" in result.reason


def test_unavailable_coverage_blocks_gap_interpretation():
    df = _df([
        {"mmsi": "333", "timestamp": "2026-01-01 11:40", "lat": 10.0, "lon": 76.0},
    ])
    result = analyze_ais_gaps(
        df, "333", datetime(2026, 1, 1, 12, 0),
        expected_interval_minutes=15, coverage_available=False,
    )
    assert result.status == "NO_COVERAGE_TO_ASSESS"
    assert result.evidence_strength == 0.0


def test_continuity_is_reported_when_observations_are_regular():
    df = _df([
        {"mmsi": "444", "timestamp": "2026-01-01 11:50", "lat": 10.0, "lon": 76.0},
        {"mmsi": "444", "timestamp": "2026-01-01 12:05", "lat": 10.01, "lon": 76.01},
        {"mmsi": "444", "timestamp": "2026-01-01 12:20", "lat": 10.02, "lon": 76.02},
    ])
    result = analyze_ais_gaps(
        df, "444", datetime(2026, 1, 1, 12, 0),
        expected_interval_minutes=15, coverage_available=True,
    )
    assert result.status == "AIS_CONTINUITY_OBSERVED"
    assert result.largest_internal_gap_minutes == 15.0


def test_serialization_preserves_non_attribution_semantics():
    df = _df([
        {"mmsi": "555", "timestamp": "2026-01-01 11:59", "lat": 10.0, "lon": 76.0},
        {"mmsi": "555", "timestamp": "2026-01-01 12:01", "lat": 10.0, "lon": 76.0},
    ])
    result = gap_analysis_to_dict(analyze_ais_gaps(
        df, "555", datetime(2026, 1, 1, 12, 0), coverage_available=True,
    ))
    assert result["responsibility_status"] == "NOT_ESTABLISHED"
    assert "does not establish" in result["interpretation"]
