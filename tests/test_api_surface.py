import importlib


def test_imw_api_surface_and_real_only_contract():
    app_module = importlib.import_module("app")
    routes = {getattr(route, "path", None): route for route in app_module.app.routes}
    assert "/api/process-sar" in routes
    assert "/api/analyze-traffic" in routes
    assert "/api/prepare-response" in routes
    assert "/api/build-report" in routes
    assert "/api/analyze-incident" in routes


def test_real_pipeline_has_explicit_integrity_markers():
    pipeline = importlib.import_module("main.imw_real_pipeline")
    source = open(pipeline.__file__, encoding="utf-8").read()
    assert '"data_integrity": "REAL_ONLY"' in source
    assert '"status": "NOT_AVAILABLE"' in source
    assert 'corroborate_rf([], 0.0, 0.0)' in source
