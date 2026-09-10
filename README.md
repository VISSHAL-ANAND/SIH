# Indo Marine Watch (IMW)

**SIH26143 — Leveraging Satellite Imagery to Determine Oil Spills at Sea Along with AIS Data Correlations to Identify Vessel Responsible for the Spill**

Indo Marine Watch is a software pipeline for maritime incident investigation. It starts from a SAR image, detects oil-slick candidates and physical vessel hulls, geolocates evidence when the source raster contains valid geospatial metadata, correlates detected hulls with AIS records, analyses vessel-history continuity, adds environmental drift evidence when real/modelled observations are available, and produces an operator-reviewed incident report and Coast Guard response draft.

> **Important:** IMW is an investigation and decision-support system. It does not declare legal responsibility, invent missing sensor data, or transmit a Coast Guard message automatically.

## Current architecture

```text
SAR image / GeoTIFF
        |
        v
Real U-Net slick inference
        |
        +--> geometric slick-shape analysis
        |
        +--> physical hull detection (YOLO)
        |        |
        |        +--> WGS84 geolocation when GeoTIFF metadata exists
        |
        +--> real AIS correlation
        |        |
        |        +--> GFW AIS presence when authorized + recent
        |        +--> documented MarineCadastre replay fallback
        |        +--> candidate vessels
        |        +--> AIS coverage / gap state
        |        +--> vessel history + trajectory evidence
        |        +--> transparent candidate ranking
        |
        +--> environmental observations
        |        |
        |        +--> current + wind vectors
        |        +--> backward drift source-zone estimate
        |
        +--> RF corroboration status
        |        `--> NOT_IMPLEMENTED until a real provider is connected
        |
        v
Canonical incident package
        |
        +--> evidence matrix / timeline / vessel investigation UI
        +--> deterministic incident report
        `--> Coast Guard response DRAFT (operator confirmation required)
```

## Data-integrity rules

The canonical `app.py` API is **real-only**:

- SAR inference uses the configured trained model; there is no fake SAR result fallback.
- GeoTIFF coordinates are marked as real geospatial evidence. Plain image coordinates are only estimated when the operator supplies an explicit image centre.
- AIS attribution uses configured real AIS records. If the source is missing, the API reports `NO_AIS_COVERAGE` / `UNAVAILABLE` rather than manufacturing vessel positions.
- An AIS gap means **an observed data gap**. It does not prove intentional AIS shutdown, spoofing, or legal responsibility.
- Environmental evidence comes from Open-Meteo Marine + Forecast APIs when available. Provider failures remain explicit `UNAVAILABLE` states.
- Drift is a modelled source-zone estimate, not a legal attribution radius.
- RF evidence is `NOT_IMPLEMENTED` until a real RF provider is connected.
- Coast Guard response generation creates a draft only: `DRAFT_REQUIRES_OPERATOR_CONFIRMATION` and `NOT_SENT`.

## Run locally

### 1. Install Python dependencies

Python 3.11 is the CI target.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Provide trained model weights

The canonical pipeline expects these files by default:

```text
data/processed/best_unet.pt
runs/detect/sar_hull_detector/weights/best_unet.pt
```

Large model binaries are intentionally excluded from Git. Override the paths without editing code:

```text
IMW_SLICK_CHECKPOINT=<path-to-trained-slick-checkpoint>
IMW_HULL_CHECKPOINT=<path-to-trained-hull-checkpoint>
```

If a required checkpoint is absent, IMW reports the dependency failure instead of silently substituting another model.

### 3. Configure AIS

For a documented historical replay, place a MarineCadastre-style AIS file at:

```text
AIS_CSV_PATH/ais-2025-01-01
```

The matcher expects columns such as `mmsi`, `base_date_time`, `longitude`, `latitude`, `vessel_name`, and related vessel metadata.

For **current/recent Indian-water coverage**, IMW now supports an opt-in Global Fishing Watch AIS-presence adapter. Configure a personal GFW API token as an environment variable:

```text
GFW_API_ACCESS_TOKEN=<your-token>
```

The provider uses GFW's `public-global-presence:latest` dataset through the 4Wings report API, queries a small polygon around the detected SAR hulls, and converts real hourly presence records into IMW's internal AIS schema. GFW API access is authenticated and permission-controlled; a 401/403 is surfaced explicitly. The current GFW AIS-presence dataset is available only to approximately 96 hours before the present, so older SAR replay scenes continue to use the documented local AIS source when available.

**Geographic limitation:** the MarineCadastre replay sample is not an Indian-water feed and must not be presented as live Indian-water AIS. For the SIH live/recent walkthrough, use an authorized GFW token and document the exact source/date.

### 4. Start the API

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open the dashboard at `http://localhost:8000`.

Useful diagnostic endpoint:

```text
GET /api/health
```

It reports checkpoint availability, AIS-source availability, environmental-provider status, and RF implementation state without running model inference.

## API surface

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Read-only deployment/dependency diagnostics |
| `POST /api/process-sar` | Canonical SAR → slick → hull → AIS → evidence pipeline |
| `POST /api/analyze-traffic` | Correlate a supplied hull location with configured AIS |
| `POST /api/analyze-drift` | Analyse operator-supplied environmental observations |
| `POST /api/prepare-response` | Build an operator-reviewed Coast Guard response draft |
| `POST /api/build-report` | Build a deterministic incident evidence report |
| `GET /` | Serve the IMW dashboard |

## Environmental evidence

The live environmental adapter uses Open-Meteo's Marine API for ocean-current information and the Forecast/Historical Forecast API for wind observations. Historical SAR timestamps are routed to the historical forecast service when current forecast data is inappropriate.

The drift calculation uses the configured windage factor (default `0.03`) and records its assumptions and uncertainty. It is intentionally presented as evidence for investigation, not as proof of where a discharge legally originated.

## Testing

The CI workflow runs the deterministic IMW contract suite covering:

- API surface and integrity markers
- health/dependency diagnostics
- SAR/investigation contract
- geolocation
- AIS candidate discovery
- candidate ranking
- vessel history and association
- trajectory evidence
- drift analysis
- environmental-provider conversions and historical routing
- Global Fishing Watch AIS-provider parsing and permission handling
- incident package/report/response contracts
- RF corroboration state

Run the contract suite locally with:

```bash
python -m pytest \
  tests/test_rf_corroboration.py \
  tests/test_incident_package.py \
  tests/test_imw_e2e_contract.py \
  tests/test_drift_analysis.py \
  tests/test_api_surface.py \
  tests/test_candidate_ranking.py \
  tests/test_ais_candidates.py \
  tests/test_geolocation_pixel_center.py \
  tests/test_incident_response.py \
  tests/test_incident_report.py \
  tests/test_prepare_response_contract.py \
  tests/test_environmental_provider.py \
  tests/test_gfw_ais_provider.py -q
```

Some tests intentionally use deterministic fixtures or monkeypatching to verify contracts without fabricating production sensor evidence.

## Repository layout

```text
app.py                         Canonical FastAPI entry point
main/
  imw_real_pipeline.py         End-to-end real pipeline
  predict_and_classify.py      U-Net inference
  shape_classifier.py          Explainable slick geometry classifier
  ship_detection_module.py     YOLO hull detection + geolocation
  ais_matcher.py               Local real AIS loading/matching
  gfw_ais_provider.py          Optional Global Fishing Watch AIS adapter
  ais_candidates.py            Multi-vessel candidate discovery
  candidate_ranking.py         Transparent evidence ranking
  vessel_history.py            AIS continuity/gap analysis
  trajectory_evidence.py       Vessel trajectory evidence
  vessel_association.py        Evidence association state
  evidence_fusion.py           Evidence confidence fusion
  environmental_provider.py    Live/modelled environment adapter
  drift_analysis.py            Backward source-zone estimate
  rf_corroboration.py          RF provider status boundary
  incident_package.py          Canonical incident schema
  incident_report.py            Report builder
  incident_response.py         Operator-reviewed response draft
  ...                          Supporting pipeline modules
static/                        IMW dashboard
t​raining/                      Dataset preparation and model training
tests/                         Contract and component tests
.github/workflows/              CI
```

## What is not claimed

IMW currently does **not** claim that an AIS gap proves a dark vessel intentionally disabled its transponder, that an environmental backtrack identifies a legally responsible source, or that an RF detection exists when no RF provider is connected. Those distinctions are part of the system's evidence model and should remain visible in the SIH demonstration.

## SIH pitch focus

The strongest software contribution is the chain from **independent SAR physical-hull evidence → time/space AIS correlation → vessel-history/trajectory analysis → environmental corroboration → auditable incident package → operator-reviewed response**. The system is designed to make each evidence source inspectable instead of collapsing uncertain signals into a fabricated certainty score.

## Release gate

Before a public SIH demo:

1. Confirm the latest GitHub Actions run for `main` is green.
2. Confirm both trained checkpoints are present locally or configured through environment variables.
3. Validate one real georeferenced Sentinel-1 scene end-to-end.
4. For a recent live walkthrough, use an authorized GFW token and record the exact AIS dataset/date used.
5. For historical replay, use the documented AIS file and label it as replay data.
6. Verify the incident map, evidence matrix, vessel investigation, report export, and Coast Guard draft workflow.
7. Keep `RESPONSIBILITY_STATUS=NOT_ESTABLISHED` unless independent evidence supports a stronger conclusion.

**Final repository verification:** the canonical contract suite must remain green after every release change.
