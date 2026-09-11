from datetime import datetime

import pandas as pd

import main.imw_real_pipeline as pipeline


class Coverage:
    status = "REAL_COVERAGE"
    coverage_confidence = "HIGH"
    reason = "Observed AIS coverage available."


def test_unified_candidate_contains_ais_trajectory_drift_and_fusion(monkeypatch):
    detection_time = datetime(2026, 6, 21, 23, 49, 0)
    ais_df = pd.DataFrame(
        [
            {"timestamp": detection_time, "lat": 19.0, "lon": 92.0, "mmsi": "123456789", "sog_knots": 8.0, "cog_degrees": 90.0},
            {"timestamp": detection_time.replace(minute=48), "lat": 19.0, "lon": 91.95, "mmsi": "123456789", "sog_knots": 8.0, "cog_degrees": 90.0},
        ]
    )
    candidate = {
        "hull_id": 0,
        "mmsi": "123456789",
        "vessel_name": "TEST VESSEL",
        "spatial_distance_km": 1.0,
        "temporal_delta_min": 5.0,
        "ais_lat": 19.0,
        "ais_lon": 92.0,
    }

    monkeypatch.setattr(pipeline, "analyze_vessel_history", lambda *args: object())
    monkeypatch.setattr(pipeline, "history_to_dict", lambda _: {"evidence_strength": 0.8})
    monkeypatch.setattr(
        pipeline,
        "analyze_trajectory",
        lambda *args: object(),
    )
    monkeypatch.setattr(
        pipeline,
        "trajectory_to_dict",
        lambda _: {"trajectory_score": 0.85, "status": "MOVEMENT_TOWARD_HULL_OBSERVED"},
    )

    base = pipeline._candidate_evidence(
        {"hull_id": 0, "lat": 19.0, "lon": 92.0},
        candidate,
        Coverage(),
        ais_df,
        detection_time,
    )
    drift = {
        "status": "ESTIMATED",
        "origin_lat": 19.005,
        "origin_lon": 91.995,
    }

    result = pipeline._apply_drift_and_fusion([base], drift)[0]

    assert result["matched_mmsi"] == "123456789"
    assert result["vessel_history"]["evidence_strength"] == 0.8
    assert result["trajectory"]["trajectory_score"] == 0.85
    assert result["drift_source_distance_km"] is not None
    assert result["drift_source_score"] is not None
    assert result["evidence_fusion"]["score"] is not None
    assert result["investigation_score"] == result["evidence_fusion"]["score"]
    assert result["investigation_classification"] == result["evidence_fusion"]["classification"]
    assert result["investigation_confidence"] == result["evidence_fusion"]["confidence"]
    assert result["investigation_evidence_coverage"] == result["evidence_fusion"]["available_weight"]
    assert result["responsibility_status"] == "NOT_ESTABLISHED"


def test_missing_drift_remains_explicitly_unavailable(monkeypatch):
    candidate = {
        "hull_id": 1,
        "mmsi": "987654321",
        "vessel_name": "TEST VESSEL 2",
        "spatial_distance_km": 2.0,
        "temporal_delta_min": 10.0,
        "ais_lat": 19.0,
        "ais_lon": 92.0,
    }
    monkeypatch.setattr(pipeline, "analyze_vessel_history", lambda *args: object())
    monkeypatch.setattr(pipeline, "history_to_dict", lambda _: {"evidence_strength": 0.7})
    monkeypatch.setattr(pipeline, "analyze_trajectory", lambda *args: object())
    monkeypatch.setattr(pipeline, "trajectory_to_dict", lambda _: {"trajectory_score": 0.6})

    ais_df = pd.DataFrame([{"timestamp": datetime(2026, 6, 21, 23, 49), "lat": 19.0, "lon": 92.0, "mmsi": "987654321"}])
    base = pipeline._candidate_evidence({"hull_id": 1, "lat": 19.0, "lon": 92.0}, candidate, Coverage(), ais_df, datetime(2026, 6, 21, 23, 49))
    result = pipeline._apply_drift_and_fusion([base], {"status": "NOT_AVAILABLE"})[0]

    assert result["drift_evidence_status"] == "NOT_AVAILABLE"
    assert result["drift_source_score"] is None
    assert result["evidence_fusion"]["components"]["drift"] is None
    assert result["responsibility_status"] == "NOT_ESTABLISHED"
