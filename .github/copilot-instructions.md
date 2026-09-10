# Indo Marine Watch — Repository Instructions

## Canonical application

- `app.py` is the only FastAPI entry point.
- Start with `uvicorn app:app --host 0.0.0.0 --port 8000`.
- Do not reintroduce duplicate FastAPI apps or legacy simulated endpoint adapters.

## Real-data policy

This repository is an SIH26143 maritime investigation system. Never fabricate production evidence.

- SAR detections must come from the configured trained model.
- Physical hull detections must remain independent of AIS.
- GeoTIFF coordinates are real only when derived from valid raster geospatial metadata.
- Plain-image coordinates must be explicitly marked estimated.
- AIS results must come from configured real records. Missing coverage is `UNAVAILABLE`/coverage state, not a fake vessel track.
- AIS gaps do not prove intentional shutdown, spoofing, or legal responsibility.
- Environmental observations must come from the configured provider or explicit operator-supplied observations.
- RF corroboration remains `NOT_IMPLEMENTED` until a real provider exists.
- Drift is modelled evidence with assumptions and uncertainty, not legal attribution.
- Coast Guard output is a draft. Never claim that a message was transmitted unless a real, audited transmission integration exists.

## Architecture

```text
SAR -> slick segmentation -> slick geometry
    -> physical hull detection -> WGS84 geolocation
    -> AIS candidate discovery -> ranking/history/trajectory
    -> environmental evidence -> drift source-zone estimate
    -> incident package -> report -> operator-reviewed response draft
```

## Code-change rules

1. Prefer the canonical `main/` runtime modules over legacy alternatives.
2. Preserve explicit status values such as `REAL_MODELLED_DATA`, `UNAVAILABLE`, `NOT_IMPLEMENTED`, `ESTIMATED`, and `NOT_ESTABLISHED`.
3. Do not add synthetic fallback paths to production endpoints.
4. Keep provider errors visible and actionable.
5. Keep deterministic tests independent from external services where possible.
6. Update tests whenever the API contract changes.
7. Update `README.md`, `PROJECT_STATUS.md`, or `EXECUTION_PLAN.md` when a material architecture/status change occurs.
8. Do not commit large AIS datasets, trained weights, temporary screenshots, or generated runtime artifacts unless explicitly required as tracked fixtures.

## Validation

The canonical CI suite is defined in `.github/workflows/imw-tests.yml`. It covers API surface, AIS candidates/ranking/history, geolocation, drift, environmental provider behaviour, incident packaging/reporting/response, and RF status boundaries.

Before merging substantial pipeline changes, verify:

- model/checkpoint paths are explicit;
- GeoTIFF and plain-image geolocation semantics are preserved;
- AIS coverage limitations are disclosed;
- environmental provider failures remain `UNAVAILABLE`;
- no legal-responsibility claim is generated automatically;
- response generation remains operator-reviewed and unsent.
