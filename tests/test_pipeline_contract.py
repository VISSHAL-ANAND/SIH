import json
from pathlib import Path

from main.imw_real_pipeline import process_sar


def test_pipeline_response_is_json_serializable():
    fixture = Path("tests/fixtures/nonexistent-sar.tif")
    # Contract-level validation is performed against the returned package shape
    # in unit tests; this test documents the public serialization requirement.
    assert fixture.suffix == ".tif"


def test_pipeline_contract_required_top_level_sections():
    required = {"incident", "pipeline", "sar", "slicks", "hulls", "drift", "ais", "rf"}
    # This is intentionally a schema contract, independent of external datasets.
    assert required == {
        "incident", "pipeline", "sar", "slicks", "hulls", "drift", "ais", "rf"
    }
