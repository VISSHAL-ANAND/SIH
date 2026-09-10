from datetime import datetime

import pandas as pd

from main.ais_matcher import assess_ais_coverage, haversine_km
from main.vessel_association import score_vessel_association


def test_haversine_distance_is_reasonable():
    distance = float(haversine_km(0.0, 0.0, 0.0, 1.0))
    assert 110.0 < distance < 112.5


def test_association_exposes_spatial_and_temporal_evidence_without_responsibility():
    result = score_vessel_association(
        hull_id=1,
        mmsi="123456789",
        vessel_name="TEST VESSEL",
        distance_km=1.0,
        time_diff_hours=0.25,
        history={"status": "CONTINUITY_OBSERVED", "evidence_strength": 0.9},
        coverage_status="LOCAL_AIS_ACTIVITY",
    )
    payload = result.__dict__
    assert payload["spatial_distance_km"] == 1.0
    assert payload["temporal_delta_min"] == 15.0
    assert payload["classification"] in {"STRONG_CANDIDATE", "POSSIBLE_CANDIDATE", "WEAK_CANDIDATE"}
    assert payload["ais_gap_status"] == "NO_GAP_OBSERVED"
    assert payload["classification"] != "RESPONSIBLE"


def test_proximity_without_mmsi_remains_unresolved():
    result = score_vessel_association(
        hull_id=2,
        mmsi=None,
        vessel_name=None,
        distance_km=0.1,
        time_diff_hours=0.01,
        history=None,
        coverage_status="LOCAL_AIS_ACTIVITY",
    )
    assert result.classification == "UNRESOLVED"
    assert result.overall_score > 0.0


def test_ais_feed_with_no_records_is_not_called_an_ais_gap():
    frame = pd.DataFrame(columns=["mmsi", "timestamp", "lat", "lon", "vessel_name"])
    result = assess_ais_coverage(
        frame,
        hull_lat=10.0,
        hull_lon=72.0,
        hull_time=datetime(2026, 9, 10, 0, 0, 0),
    )
    assert result.status == "NO_AIS_COVERAGE"
    assert result.coverage_confidence == 0.0


def test_local_activity_plus_post_event_history_gap_is_only_potential():
    history = {
        "status": "POST_EVENT_GAP_UNRESOLVED",
        "evidence_strength": 0.25,
    }
    result = score_vessel_association(
        hull_id=3,
        mmsi="987654321",
        vessel_name="TEST",
        distance_km=2.0,
        time_diff_hours=0.5,
        history=history,
        coverage_status="LOCAL_AIS_ACTIVITY",
    )
    assert result.ais_gap_status == "POTENTIAL_GAP_REQUIRES_REVIEW"
    assert result.classification != "RESPONSIBLE"
