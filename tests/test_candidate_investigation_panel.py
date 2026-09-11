from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "static" / "candidate-investigation-panel.js"
INDEX = ROOT / "static" / "index.html"
INTEGRATION = ROOT / "static" / "imw-integration.js"


def test_candidate_panel_exposes_render_hook_and_core_evidence():
    text = PANEL.read_text(encoding="utf-8")
    assert "window.renderCandidateInvestigationPanel" in text
    for field in (
        "spatial_distance_km",
        "temporal_delta_min",
        "ais_gap_status",
        "trajectory.trajectory_score",
        "drift_source_score",
        "evidence_fusion",
    ):
        assert field in text


def test_candidate_panel_is_operator_safe():
    text = PANEL.read_text(encoding="utf-8")
    assert "Responsibility: NOT ESTABLISHED" in text
    assert "AIS gaps do not prove intentional shutdown" in text
    assert "not a legal attribution radius" in text
    assert "imw:candidate-selected" in text


def test_candidate_panel_is_loaded_before_integration_and_map():
    index = INDEX.read_text(encoding="utf-8")
    assert "/static/candidate-investigation-panel.js" in index
    assert index.index("/static/candidate-investigation-panel.js") < index.index("/static/imw-integration.js")
    assert index.index("/static/candidate-investigation-panel.js") < index.index("/static/investigation-map.js")


def test_canonical_sync_renders_selected_candidate_panel():
    text = INTEGRATION.read_text(encoding="utf-8")
    assert "renderCandidateInvestigationPanel(first)" in text
