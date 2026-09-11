"""Regression tests for explainable IMW evidence fusion."""

from main.evidence_fusion import fuse_evidence, fusion_to_dict


def test_full_evidence_fuses_to_strong_candidate():
    result = fuse_evidence(0.95, 0.9, 0.85, 0.9, 0.8)
    assert result.score >= 0.80
    assert result.classification == "STRONG_CANDIDATE"
    assert result.confidence == "HIGH"
    assert result.available_weight == 1.0


def test_missing_drift_does_not_penalize_other_observed_evidence():
    result = fuse_evidence(0.9, 0.9, 0.8, 0.8, None)
    assert result.score >= 0.80
    assert result.available_weight == 0.70
    assert "drift evidence unavailable" in result.limitations


def test_only_drift_evidence_is_low_confidence():
    result = fuse_evidence(None, None, None, None, 0.9)
    assert result.score == 0.9
    assert result.available_weight == 0.30
    assert result.confidence == "LOW"
    assert result.classification == "WEAK_CANDIDATE"


def test_no_evidence_is_unresolved():
    result = fuse_evidence(None, None, None, None, None)
    payload = fusion_to_dict(result)
    assert payload["score"] is None
    assert payload["classification"] == "UNRESOLVED"
    assert payload["confidence"] == "INSUFFICIENT_DATA"


def test_scores_are_clamped_and_serialized():
    result = fuse_evidence(2.0, -1.0, None, None, 0.5)
    payload = fusion_to_dict(result)
    assert payload["score"] is not None
    assert 0.0 <= payload["score"] <= 1.0
    assert payload["components"]["spatial"] == 2.0
