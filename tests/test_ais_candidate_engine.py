from datetime import datetime

import pandas as pd

from main.ais_candidates import find_ais_candidates


def test_returns_multiple_distinct_candidates_with_evidence_fields():
    event = datetime(2026, 6, 21, 23, 49, 0)
    ais = pd.DataFrame(
        [
            {
                "mmsi": "111000111",
                "timestamp": datetime(2026, 6, 21, 23, 40, 0),
                "lat": 19.8005,
                "lon": 92.4170,
                "vessel_name": "ALPHA",
                "sog": 12.4,
                "cog": 85.0,
                "heading": 86.0,
                "imo": "IMO111",
                "call_sign": "ALP1",
                "vessel_type": "Cargo",
                "status": "Under way",
            },
            {
                "mmsi": "222000222",
                "timestamp": datetime(2026, 6, 21, 23, 55, 0),
                "lat": 19.8015,
                "lon": 92.4175,
                "vessel_name": "BRAVO",
                "sog": 8.0,
                "cog": 270.0,
                "heading": 268.0,
                "imo": "IMO222",
                "call_sign": "BRV2",
                "vessel_type": "Tanker",
                "status": "Under way",
            },
            # Same MMSI as ALPHA but farther away: should not create a duplicate.
            {
                "mmsi": "111000111",
                "timestamp": datetime(2026, 6, 21, 23, 45, 0),
                "lat": 19.81,
                "lon": 92.43,
                "vessel_name": "ALPHA",
            },
        ]
    )

    candidates = find_ais_candidates(
        19.8000,
        92.4170,
        event,
        ais,
        hull_id=7,
        radius_km=5.0,
        time_hours=2.0,
    )

    assert len(candidates) == 2
    assert {c["mmsi"] for c in candidates} == {"111000111", "222000222"}
    alpha = next(c for c in candidates if c["mmsi"] == "111000111")
    assert alpha["vessel_name"] == "ALPHA"
    assert alpha["sog_knots"] == 12.4
    assert alpha["cog_degrees"] == 85.0
    assert alpha["imo"] == "IMO111"
    assert alpha["call_sign"] == "ALP1"
    assert alpha["ais_candidate_status"] == "OBSERVED_NEAR_SAR_HULL"
    assert alpha["responsibility_status"] == "NOT_ESTABLISHED"


def test_enforces_both_spatial_and_temporal_windows():
    event = datetime(2026, 6, 21, 23, 49, 0)
    ais = pd.DataFrame(
        [
            {"mmsi": "111", "timestamp": datetime(2026, 6, 21, 23, 50), "lat": 19.8, "lon": 92.417},
            {"mmsi": "222", "timestamp": datetime(2026, 6, 21, 23, 50), "lat": 20.0, "lon": 92.417},
            {"mmsi": "333", "timestamp": datetime(2026, 6, 22, 2, 0), "lat": 19.8, "lon": 92.417},
        ]
    )

    candidates = find_ais_candidates(
        19.8,
        92.417,
        event,
        ais,
        radius_km=5.0,
        time_hours=2.0,
    )

    assert [c["mmsi"] for c in candidates] == ["111"]


def test_empty_or_invalid_feed_is_explicitly_empty():
    event = datetime(2026, 6, 21, 23, 49, 0)
    assert find_ais_candidates(19.8, 92.417, event, pd.DataFrame()) == []
    assert find_ais_candidates(19.8, 92.417, event, pd.DataFrame({"lat": [19.8]})) == []
