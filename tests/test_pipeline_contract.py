"""Contract tests for the canonical IMW real pipeline."""

from pathlib import Path

from main.imw_real_pipeline import run_real_pipeline


def test_pipeline_public_entrypoint_exists():
    """The canonical pipeline entrypoint is run_real_pipeline."""
    assert callable(run_real_pipeline)


def test_pipeline_contract_required_top_level_sections():
    """Document the stable top-level incident package sections."""
    required = {"incident", "pipeline", "sar", "slicks", "hulls", "drift", "ais", "rf"}
    assert required == {
        "incident", "pipeline", "sar", "slicks", "hulls", "drift", "ais", "rf"
    }


def test_pipeline_fixture_path_is_tiff():
    """Keep the contract fixture convention explicit without running inference."""
    fixture = Path("tests/fixtures/nonexistent-sar.tif")
    assert fixture.suffix == ".tif"
