from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAP_JS = ROOT / "static" / "investigation-map.js"
INDEX_HTML = ROOT / "static" / "index.html"


def test_investigation_map_separates_observed_and_estimated_evidence():
    text = MAP_JS.read_text(encoding="utf-8")
    assert "OBSERVED / SAR" in text
    assert "OBSERVED / AIS" in text
    assert "OBSERVED / AIS TRACK" in text
    assert "ESTIMATED / ENVIRONMENTAL MODEL" in text
    assert "not a legal attribution radius" in text


def test_investigation_map_renders_trajectory_and_drift_zone():
    text = MAP_JS.read_text(encoding="utf-8")
    assert "candidate?.trajectory?.points" in text
    assert "L.polyline(track" in text
    assert "L.circle(origin" in text
    assert "candidate.vessel_name" in text


def test_investigation_map_is_loaded_after_app():
    text = INDEX_HTML.read_text(encoding="utf-8")
    app_pos = text.index('/static/app.js')
    map_pos = text.index('/static/investigation-map.js')
    assert map_pos > app_pos
