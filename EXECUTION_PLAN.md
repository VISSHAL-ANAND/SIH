# IMW Execution Plan

**Updated:** 2026-09-10

This plan describes the current canonical Indo Marine Watch implementation. Older phase notes and superseded mock-pipeline instructions are intentionally not repeated here.

## 1. Runtime contract

Use `app.py` as the only FastAPI entry point:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Do not restore the removed duplicate `main.py` applications or simulated endpoint adapters.

## 2. Evidence pipeline

### Step A — SAR

- Load a real SAR image/GeoTIFF.
- Run the trained U-Net checkpoint.
- Convert the binary prediction into connected slick components.
- Classify slick geometry using the explainable PCA/elongation classifier.

### Step B — Hull

- Run the trained YOLO hull detector.
- Keep physical hull detections independent from AIS.
- If the source is a georeferenced raster, convert pixel-centre coordinates to WGS84.
- If the source is a plain image, only use an explicitly supplied centre and mark the resulting location as estimated.

### Step C — AIS

- Load configured real AIS data.
- Search a bounded spatial/temporal window around each georeferenced hull.
- Preserve all distinct nearby candidate MMSIs rather than forcing a single match.
- Rank candidates using spatial, temporal, continuity, and trajectory evidence.
- Represent missing coverage and AIS gaps explicitly.

### Step D — Vessel evidence

For each candidate, retain:

- MMSI and vessel name when present
- spatial separation
- temporal separation
- AIS coverage state
- vessel-history continuity
- pre/post-event positions when available
- trajectory evidence
- transparent ranking reasons
- `responsibility_status = NOT_ESTABLISHED`

An AIS gap is evidence of missing observations, not proof of intentional shutdown or responsibility.

### Step E — Environment and drift

Use `main/environmental_provider.py` for current/wind observations.

- Current direction is converted to a velocity vector.
- Wind direction is interpreted as the direction the wind comes from and converted accordingly.
- Historical SAR timestamps use the historical forecast service where appropriate.
- Provider failure becomes `UNAVAILABLE`; no synthetic environment is inserted.
- `main/drift_analysis.py` estimates a backward source zone and records assumptions/uncertainty.

### Step F — Response/report

- Build the canonical incident package.
- Render the investigation dashboard.
- Build a deterministic evidence report.
- Generate a Coast Guard response **draft** only.
- Require operator confirmation before any future transmission integration.

## 3. External-data readiness

### AIS

Current MarineCadastre data is real but geographically unsuitable for an Indian-water pitch. Treat it as matcher validation data only.

Next step: connect a permitted Indian/global AIS provider. If access fails, show `UNAVAILABLE` rather than inventing coverage.

### RF

RF corroboration is deliberately not implemented until a real provider is connected.

### SAR

The strongest final demonstration should use a real georeferenced Sentinel-1 scene so both the slick and hull coordinates are grounded in raster metadata.

## 4. Validation gates

Before calling the project pitch-ready:

- [ ] CI contract suite is green.
- [ ] U-Net checkpoint loads successfully.
- [ ] YOLO checkpoint loads successfully.
- [ ] One real GeoTIFF passes the complete pipeline.
- [ ] The resulting WGS84 coordinates are manually sanity-checked.
- [ ] AIS source/date/coverage are documented for the exact demo scene.
- [ ] Environmental observations are timestamp-compatible with the SAR event.
- [ ] Drift assumptions and uncertainty are visible to the operator.
- [ ] No demo screen claims legal responsibility from model output alone.
- [ ] Coast Guard response remains a draft until operator confirmation.

## 5. CI contract suite

GitHub Actions runs:

```text
test_rf_corroboration
test_incident_package
test_imw_e2e_contract
test_drift_analysis
test_api_surface
test_candidate_ranking
test_ais_candidates
test_geolocation_pixel_center
test_incident_response
test_incident_report
test_prepare_response_contract
test_environmental_provider
```

Run locally with:

```bash
python -m pytest tests/test_rf_corroboration.py tests/test_incident_package.py tests/test_imw_e2e_contract.py tests/test_drift_analysis.py tests/test_api_surface.py tests/test_candidate_ranking.py tests/test_ais_candidates.py tests/test_geolocation_pixel_center.py tests/test_incident_response.py tests/test_incident_report.py tests/test_prepare_response_contract.py tests/test_environmental_provider.py -q
```

## 6. Final SIH sequence

**Clean repository → green CI → real GeoTIFF validation → real Indian/global AIS → curated evidence walkthrough → final pitch deck.**
