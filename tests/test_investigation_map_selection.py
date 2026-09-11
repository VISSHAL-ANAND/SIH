from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "investigation-map.js"


def test_map_exposes_candidate_selection_hook():
    text = JS.read_text(encoding="utf-8")
    assert "window.selectInvestigationCandidate" in text
    assert "imw:candidate-selected" in text


def test_map_click_selection_updates_visual_state_and_panel():
    text = JS.read_text(encoding="utf-8")
    assert "__imwSelectedCandidateKey" in text
    assert "renderVesselInvestigation(candidate)" in text
    assert "__imwInvestigationCandidateMarkers" in text


def test_map_keeps_responsibility_unestablished():
    text = JS.read_text(encoding="utf-8")
    assert "responsibility is not established" in text
    assert "legal attribution radius" in text
