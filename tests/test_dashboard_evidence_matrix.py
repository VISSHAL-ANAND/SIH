from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_evidence_matrix_displays_final_investigation_fields():
    text = (ROOT / "static" / "evidence-matrix.js").read_text(encoding="utf-8")
    for marker in (
        "Unified investigation score",
        "investigation_score",
        "investigation_classification",
        "investigation_confidence",
        "investigation_evidence_coverage",
        "drift_source_score",
        "responsibility",
    ):
        assert marker in text


def test_dashboard_uses_canonical_incident_candidate():
    text = (ROOT / "static" / "imw-integration.js").read_text(encoding="utf-8")
    assert "incident.candidates" in text
    assert "renderEvidenceMatrix(first)" in text
    assert "window.imwCanonicalIncident = incident" in text
