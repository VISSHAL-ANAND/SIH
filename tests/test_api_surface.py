import importlib


def test_imw_api_surface_and_real_only_contract():
    app_module = importlib.import_module("app")
    routes = {getattr(route, "path", None): route for route in app_module.app.routes}
    assert "/api/process-sar" in routes
    assert "/api/analyze-traffic" in routes
    assert "/api/analyze-drift" in routes
    assert "/api/prepare-response" in routes
    assert "/api/build-report" in routes
    assert "/api/analyze-incident" not in routes


def test_environmental_observation_parser_rejects_non_list_payloads():
    app_module = importlib.import_module("app")
    try:
        app_module._parse_environmental_observations('{"timestamp": "2026-06-21T22:50:00Z"}')
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
    else:
        raise AssertionError("Expected HTTP 422 for a non-list environmental payload")


def test_environmental_observation_parser_accepts_a_list_of_records():
    app_module = importlib.import_module("app")
    observations = app_module._parse_environmental_observations(
        '[{"timestamp":"2026-06-21T22:50:00Z","current_u_mps":1.0,"current_v_mps":0.0}]'
    )
    assert len(observations) == 1
    assert observations[0]["current_u_mps"] == 1.0


def test_real_pipeline_has_explicit_integrity_markers():
    pipeline = importlib.import_module("main.imw_real_pipeline")
    drift = importlib.import_module("main.drift_analysis")
    pipeline_source = open(pipeline.__file__, encoding="utf-8").read()
    drift_source = open(drift.__file__, encoding="utf-8").read()
    assert '"data_integrity": "REAL_ONLY"' in pipeline_source
    assert 'NOT_AVAILABLE' in drift_source
    assert 'corroborate_rf([], 0.0, 0.0)' in pipeline_source
