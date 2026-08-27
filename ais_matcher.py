"""
SIH26143 - AIS Matching
Built by VISSHAL
Task: Spatial-temporal hull-vs-AIS matcher + no-match suspect flagging

CORE IDEA:
For each detected ship/hull, search AIS position reports within:
    1. A distance tolerance
    2. A time tolerance

If an AIS match exists:
    -> Vessel identified
    -> Legitimate AIS presence

If NO AIS match exists:
    -> Flag as SUSPECT
    -> Possible AIS-off / dark vessel / spoofing

IMPORTANT:
AIS data is observational evidence. A missing AIS broadcast does NOT by
itself prove illegal activity.
"""

import numpy as np
import pandas as pd

from dataclasses import dataclass
from datetime import datetime, timedelta


# =============================================================================
# CONFIGURATION
# =============================================================================

# Your actual MarineCadastre AIS file.
# IMPORTANT: your file does NOT have a .csv extension.
AIS_CSV_PATH = r"A:\SIH\AIS_CSV_PATH\ais-2025-01-01"

# Maximum distance between detected hull and AIS position.
DISTANCE_TOLERANCE_KM = 5.0

# Maximum time difference between detected hull and AIS position.
TIME_TOLERANCE_HOURS = 2.0


# =============================================================================
# RESULT DATA STRUCTURE
# =============================================================================

@dataclass
class AISMatchResult:
    hull_id: int
    has_ais_match: bool
    matched_mmsi: str | None
    matched_vessel_name: str | None
    distance_km: float | None
    time_diff_hours: float | None
    suspicion_score: float
    reason: str


# =============================================================================
# HAVERSINE DISTANCE
# =============================================================================

def haversine_km(lat1, lon1, lat2, lon2):
    """
    Calculate great-circle distance between two latitude/longitude points.

    Returns distance in kilometers.
    """

    R = 6371.0

    lat1, lon1, lat2, lon2 = map(
        np.radians,
        [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    return 2 * R * np.arcsin(np.sqrt(a))


# =============================================================================
# LOAD REAL MARINECADASTRE AIS DATA
# =============================================================================

def load_ais_data(csv_path: str) -> pd.DataFrame:
    """
    Load MarineCadastre AIS data.

    Your actual file has columns:

        mmsi
        base_date_time
        longitude
        latitude
        sog
        cog
        heading
        vessel_name
        imo
        call_sign
        vessel_type
        status
        length
        width
        draft
        cargo
        transceiver

    We only load the columns required for AIS matching.
    """

    print(f"Loading AIS data from:")
    print(f"  {csv_path}")
    print()

    # Only load columns required by the matcher.
    # This reduces memory usage considerably.
    df = pd.read_csv(
        csv_path,
        usecols=[
            "mmsi",
            "base_date_time",
            "longitude",
            "latitude",
            "vessel_name",
        ],
        low_memory=True,
    )

    # Rename MarineCadastre columns to our internal names.
    df = df.rename(
        columns={
            "base_date_time": "timestamp",
            "longitude": "lon",
            "latitude": "lat",
        }
    )

    # Convert timestamp.
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce"
    )

    # Convert coordinates to numeric.
    df["lat"] = pd.to_numeric(
        df["lat"],
        errors="coerce"
    )

    df["lon"] = pd.to_numeric(
        df["lon"],
        errors="coerce"
    )

    # Make MMSI a string.
    # This avoids accidental loss of formatting.
    df["mmsi"] = df["mmsi"].astype(str)

    # Remove invalid records.
    df = df.dropna(
        subset=[
            "mmsi",
            "timestamp",
            "lat",
            "lon",
        ]
    )

    # Remove impossible geographic coordinates.
    df = df[
        (df["lat"] >= -90)
        & (df["lat"] <= 90)
        & (df["lon"] >= -180)
        & (df["lon"] <= 180)
    ]

    # Make sure vessel_name exists.
    if "vessel_name" not in df.columns:
        df["vessel_name"] = None

    print(f"Successfully loaded {len(df):,} AIS records.")
    print()

    return df


# =============================================================================
# MATCH ONE HULL TO AIS
# =============================================================================

def match_hull_to_ais(
    hull_lat: float,
    hull_lon: float,
    hull_time: datetime,
    ais_df: pd.DataFrame,
    hull_id: int
) -> AISMatchResult:

    """
    Determine whether a detected hull has a nearby AIS broadcast.

    Matching requires BOTH:

        distance <= DISTANCE_TOLERANCE_KM

        AND

        time difference <= TIME_TOLERANCE_HOURS
    """

    # -------------------------------------------------------------------------
    # STEP 1: TIME FILTER
    # -------------------------------------------------------------------------

    time_diffs = (
        ais_df["timestamp"] - hull_time
    ).abs()

    time_mask = (
        time_diffs
        <= timedelta(hours=TIME_TOLERANCE_HOURS)
    )

    candidates = ais_df[time_mask].copy()

    # No AIS records around the detection time.
    if len(candidates) == 0:

        return AISMatchResult(
            hull_id=hull_id,
            has_ais_match=False,
            matched_mmsi=None,
            matched_vessel_name=None,
            distance_km=None,
            time_diff_hours=None,
            suspicion_score=0.90,
            reason=(
                f"No AIS broadcasts found within "
                f"{TIME_TOLERANCE_HOURS} hours of detection time."
            ),
        )

    # -------------------------------------------------------------------------
    # STEP 2: DISTANCE FILTER
    # -------------------------------------------------------------------------

    candidates["distance_km"] = haversine_km(
        hull_lat,
        hull_lon,
        candidates["lat"].values,
        candidates["lon"].values
    )

    within_range = candidates[
        candidates["distance_km"]
        <= DISTANCE_TOLERANCE_KM
    ]

    # -------------------------------------------------------------------------
    # STEP 3: NO NEARBY AIS
    # -------------------------------------------------------------------------

    if len(within_range) == 0:

        nearest = candidates.loc[
            candidates["distance_km"].idxmin()
        ]

        nearest_distance = float(
            nearest["distance_km"]
        )

        # Higher distance = higher suspicion.
        suspicion = min(
            0.95,
            0.50 + nearest_distance / 50
        )

        return AISMatchResult(
            hull_id=hull_id,
            has_ais_match=False,
            matched_mmsi=None,
            matched_vessel_name=None,
            distance_km=round(
                nearest_distance,
                2
            ),
            time_diff_hours=None,
            suspicion_score=round(
                suspicion,
                2
            ),
            reason=(
                f"Nearest AIS ping was "
                f"{nearest_distance:.1f} km away -- "
                f"outside the "
                f"{DISTANCE_TOLERANCE_KM} km tolerance. "
                f"Possible AIS-off or spoofing."
            ),
        )

    # -------------------------------------------------------------------------
    # STEP 4: FIND BEST MATCH
    # -------------------------------------------------------------------------

    best = within_range.loc[
        within_range["distance_km"].idxmin()
    ]

    best_distance = float(
        best["distance_km"]
    )

    time_difference = abs(
        (
            best["timestamp"]
            - hull_time
        ).total_seconds()
    ) / 3600

    vessel_name = best.get(
        "vessel_name"
    )

    # Handle NaN vessel names.
    if pd.isna(vessel_name):
        vessel_name = None
    else:
        vessel_name = str(vessel_name).strip()

    return AISMatchResult(
        hull_id=hull_id,
        has_ais_match=True,
        matched_mmsi=str(best["mmsi"]),
        matched_vessel_name=vessel_name,
        distance_km=round(
            best_distance,
            2
        ),
        time_diff_hours=round(
            time_difference,
            2
        ),
        suspicion_score=0.0,
        reason=(
            f"Matched to MMSI {best['mmsi']} "
            f"({best_distance:.1f} km, "
            f"{time_difference:.1f} h away)."
        ),
    )


# =============================================================================
# MATCH ALL DETECTED HULLS
# =============================================================================

def match_all_hulls(
    hulls: list[dict],
    ais_df: pd.DataFrame
) -> list[AISMatchResult]:

    """
    Match every detected hull against AIS data.

    Each hull should contain:

        hull_id
        lat
        lon
        timestamp

    Results are sorted with highest suspicion first.
    """

    results = []

    for hull in hulls:

        result = match_hull_to_ais(
            hull["lat"],
            hull["lon"],
            hull["timestamp"],
            ais_df,
            hull["hull_id"]
        )

        results.append(result)

    # Highest suspicion first.
    results.sort(
        key=lambda r: r.suspicion_score,
        reverse=True
    )

    return results


# =============================================================================
# SYNTHETIC AIS DATA
# =============================================================================

def generate_synthetic_ais(
    n_vessels=20,
    seed=42
) -> pd.DataFrame:

    """
    Generate fake AIS data for testing matcher logic.

    DO NOT present synthetic results as real vessel identification.
    """

    rng = np.random.default_rng(seed)

    base_time = datetime(
        2026,
        8,
        20,
        12,
        0,
        0
    )

    rows = []

    for i in range(n_vessels):

        mmsi = 200000000 + i

        lat = (
            20.75
            + rng.random() * 0.2
        )

        lon = (
            69.10
            + rng.random() * 0.25
        )

        ts = (
            base_time
            + timedelta(
                minutes=int(
                    rng.integers(-60, 60)
                )
            )
        )

        rows.append(
            {
                "mmsi": mmsi,
                "lat": lat,
                "lon": lon,
                "timestamp": ts,
                "vessel_name": (
                    f"SYNTH_VESSEL_{i}"
                ),
            }
        )

    return pd.DataFrame(rows)


# =============================================================================
# REAL AIS SELF-TEST
# =============================================================================

if __name__ == "__main__":

    print("=" * 70)
    print("SIH26143 - AIS MATCHING SYSTEM")
    print("=" * 70)
    print()

    # -------------------------------------------------------------------------
    # LOAD REAL AIS DATA
    # -------------------------------------------------------------------------

    ais_df = load_ais_data(
        AIS_CSV_PATH
    )

    # -------------------------------------------------------------------------
    # SHOW FIRST AIS RECORD
    # -------------------------------------------------------------------------

    first_ais = ais_df.iloc[0]

    print("First AIS record:")
    print(
        f"  MMSI      : {first_ais['mmsi']}"
    )
    print(
        f"  Vessel    : {first_ais['vessel_name']}"
    )
    print(
        f"  Latitude  : {first_ais['lat']}"
    )
    print(
        f"  Longitude : {first_ais['lon']}"
    )
    print(
        f"  Timestamp : {first_ais['timestamp']}"
    )
    print()

    # -------------------------------------------------------------------------
    # TEST HULLS
    # -------------------------------------------------------------------------
    #
    # Hull 0:
    # Placed EXACTLY on the first real AIS record.
    # Expected -> MATCHED
    #
    # Hull 1:
    # Located far away.
    # Expected -> SUSPECT
    #

    test_hulls = [

        {
            "hull_id": 0,

            # Exact location of first real AIS record.
            "lat": first_ais["lat"],
            "lon": first_ais["lon"],

            # Exact timestamp of first AIS record.
            "timestamp": first_ais["timestamp"],
        },

        {
            "hull_id": 1,

            # Deliberately far away.
            "lat": 25.0,
            "lon": 75.0,

            # Same AIS date.
            "timestamp": datetime(
                2025,
                1,
                1,
                12,
                0,
                0
            ),
        },
    ]

    # -------------------------------------------------------------------------
    # RUN MATCHING
    # -------------------------------------------------------------------------

    print("=" * 70)
    print("RUNNING AIS MATCH TEST")
    print("=" * 70)
    print()

    results = match_all_hulls(
        test_hulls,
        ais_df
    )

    # -------------------------------------------------------------------------
    # DISPLAY RESULTS
    # -------------------------------------------------------------------------

    for result in results:

        if result.has_ais_match:
            status = "MATCHED"
        else:
            status = "SUSPECT"

        print(
            f"Hull {result.hull_id}: "
            f"{status}"
        )

        print(
            f"  Suspicion Score : "
            f"{result.suspicion_score}"
        )

        print(
            f"  MMSI            : "
            f"{result.matched_mmsi}"
        )

        print(
            f"  Vessel          : "
            f"{result.matched_vessel_name}"
        )

        print(
            f"  Distance        : "
            f"{result.distance_km} km"
        )

        print(
            f"  Time Difference : "
            f"{result.time_diff_hours} h"
        )

        print(
            f"  Reason          : "
            f"{result.reason}"
        )

        print("-" * 70)

    # -------------------------------------------------------------------------
    # SELF-TEST ASSERTIONS
    # -------------------------------------------------------------------------

    # Because results are sorted by suspicion,
    # the far-away hull should be first.
    assert (
        results[0].hull_id == 1
    ), "FAILED: far hull should be top suspect"

    assert (
        not results[0].has_ais_match
    ), "FAILED: far hull should NOT match"

    # At least one real AIS match must exist.
    assert any(
        r.has_ais_match
        for r in results
    ), "FAILED: nearby hull should have matched"

    print()
    print("=" * 70)
    print("SELF-TEST PASSED")
    print("=" * 70)
    print()
    print(
        "Real MarineCadastre AIS data is being loaded successfully."
    )
    print(
        "The matcher can identify nearby AIS vessels and flag"
    )
    print(
        "hulls with no nearby AIS broadcast as suspects."
    )
    print()