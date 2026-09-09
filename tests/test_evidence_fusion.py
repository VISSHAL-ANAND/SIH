from main.evidence_fusion import fuse_evidence


def test_fusion_renormalizes_available_sources():
    result = fuse_evidence(0.9, 0.8, None, 0.7, None)
    assert result.score is not None
    assert result.available_weight == 0.55
    assert "drift evidence unavailable" in result.limitations
    assert "rf" not in result.components


def test_no_evidence_is_unresolved():
    result = fuse_evidence(None, None, None, None, None)
    assert result.score is None
    assert result.classification == "UNRESOLVED"
    assert result.confidence == "INSUFFICIENT_DATA"
