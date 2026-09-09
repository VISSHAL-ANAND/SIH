"""
SIH26143 - Pipeline Integration: Data Contracts
Task: Define end-to-end pipeline interfaces/data contracts
Taken over from RATHIMEENA by VISSHAL, 2026-08-25 (last day of sprint)

WHY THIS FILE EXISTS: four people built four separate pieces (slick
detection, hull detection, AIS matching, drift simulation) without agreeing
on exact input/output shapes first. This file is the single source of truth
for what each module produces and consumes, so integration_pipeline.py can
wire them together without everyone re-negotiating formats at the last
minute.

STATUS OF EACH CONTRACT BELOW:
  - SlickDetection  : CONFIRMED REAL -- matches VISSHAL's actual
                       predict_and_classify.py output exactly.
  - HullDetection   : ASSUMED -- based on RINOSH's task description
                       ("bounding boxes + coordinates + timestamp"). Confirm
                       against his actual code and adjust if it differs.
  - AISMatchResult  : ASSUMED -- based on ASHMIL's task description
                       ("no-match hulls flagged + confidence score"). Same
                       caveat -- confirm against his real output.
  - DriftResult     : ASSUMED -- based on SIMI's task description (origin
                       point + jurisdiction zone). SIMI's NOAA data pull is
                       done but the simulation itself isn't built yet, so
                       this is a forward-looking contract, not yet verified
                       against real code.

Whoever finishes RINOSH/ASHMIL/SIMI's modules: check your actual return
values against the dataclass fields below. If they don't match, either
adjust your code to match this contract, or tell whoever owns integration
so this file gets updated -- don't let two versions of "the truth" exist.
"""

from dataclasses import dataclass, field


@dataclass
class SlickComponent:
    """One detected oil slick region within a single SAR image.
    CONFIRMED REAL -- matches shape_classifier.py / predict_and_classify.py exactly."""
    component_id: int
    area_pixels: int
    centroid_x: float          # pixel coordinates within the image
    centroid_y: float
    bbox: tuple                # (x_min, y_min, x_max, y_max) in pixel coords
    elongation_ratio: float    # 0 = perfectly linear, 1 = perfectly circular
    shape_class: str           # "linear" or "blob"
    aspect_ratio: float
    orientation_deg: float
    spill_area_sq_meters: float = 0.0  # assumes 10 m × 10 m SAR pixels


@dataclass
class SlickDetectionResult:
    """Output of VISSHAL's module for one SAR image."""
    image_id: str
    components: list[SlickComponent] = field(default_factory=list)
    num_linear: int = 0
    num_blob: int = 0


@dataclass
class HullDetection:
    """One detected vessel hull within a single SAR image.
    CONFIRMED REAL -- matches RINOSH's actual ship_detection_module.py output
    (verified independently: geo-conversion math checked against hand-computed
    values for both plain lat/lon and UTM-projected rasters, both PASSED)."""
    hull_id: int
    bbox: tuple                # (x_min, y_min, x_max, y_max) in pixel coords
    centroid_x: float
    centroid_y: float
    confidence: float          # RINOSH's detector's real confidence score, 0-1
    timestamp: str | None = None   # ISO 8601 -- from Sentinel-1 filename or file mtime
    # lat/lon are REAL when the input is a georeferenced raster (GeoTIFF with
    # a valid transform). They are None for plain jpg/png chips with no geo
    # metadata -- which is what our current Kaggle training/demo images are.
    # Use geolocation.py's demo-anchor approach as a fallback ONLY when these
    # are None; never overwrite a real lat/lon with a demo-anchor guess.
    lat: float | None = None
    lon: float | None = None
    rf_emission_detected: bool = False


@dataclass
class HullDetectionResult:
    """Output of RINOSH's module for one SAR image."""
    image_id: str
    hulls: list[HullDetection] = field(default_factory=list)


@dataclass
class AISMatch:
    """Result of matching one detected hull against AIS broadcast data.
    CONFIRMED REAL -- matches VISSHAL's actual ais_matcher.py output
    (self-tested: correctly matches nearby AIS pings, correctly flags
    distant hulls as high-suspicion)."""
    hull_id: int
    has_ais_match: bool
    matched_mmsi: str | None = None       # vessel ID if matched, else None
    suspicion_score: float = 0.0          # 0 = definitely legitimate, 1 = top suspect
    reason: str = ""                       # human-readable explanation for the pitch/dashboard


@dataclass
class AISMatchResult:
    """Output of ASHMIL's module for one SAR image."""
    image_id: str
    matches: list[AISMatch] = field(default_factory=list)


@dataclass
class DriftResult:
    """Backward drift simulation result -- estimated origin of a slick.
    ASSUMED -- SIMI's simulation isn't built yet, this is a forward contract."""
    slick_component_id: int
    estimated_origin_lat: float
    estimated_origin_lon: float
    estimated_origin_time_offset_hours: float   # how far back from detection time
    jurisdiction_zone: str                       # e.g. ICG zone name
    within_500m_exclusion: bool


@dataclass
class DriftSimResult:
    """Output of SIMI's module for one SAR image."""
    image_id: str
    drift_estimates: list[DriftResult] = field(default_factory=list)


@dataclass
class PipelineOutput:
    """Final combined output for one SAR image -- what the dashboard and
    demo walkthrough actually consume. This is the end product of
    integration_pipeline.py."""
    image_id: str
    slicks: SlickDetectionResult
    hulls: HullDetectionResult | None = None
    ais_matches: AISMatchResult | None = None
    drift: DriftSimResult | None = None

    def to_dict(self) -> dict:
        """Serialize the final pipeline payload for dashboards and APIs."""
        return {
            "image_id": self.image_id,
            "slicks": [
                {
                    "component_id": component.component_id,
                    "shape_class": component.shape_class,
                    "spill_area_sq_meters": component.spill_area_sq_meters,
                }
                for component in self.slicks.components
            ],
        }

    def top_suspects(self) -> list[dict]:
        """The actual pitch payload: hulls with no AIS match, ranked by
        suspicion score. Returns empty list until ais_matches is populated."""
        if self.ais_matches is None:
            return []
        unmatched = [m for m in self.ais_matches.matches if not m.has_ais_match]
        unmatched.sort(key=lambda m: m.suspicion_score, reverse=True)
        return [
            {"hull_id": m.hull_id, "suspicion_score": m.suspicion_score, "reason": m.reason}
            for m in unmatched
        ]
