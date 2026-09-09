"""Phase 4D — deterministic AIS investigation window helpers.

The module is provider-neutral: callers supply normalized AIS observations.
It never interprets an AIS gap as intentional interference.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _parse(ts: str) -> datetime:
    value = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_ais_window(detection_time: str, before_minutes: int = 30, after_minutes: int = 30) -> dict:
    detected = _parse(detection_time)
    return {
        "detection_time": detected.isoformat(),
        "before": {
            "start": (detected - timedelta(minutes=before_minutes)).isoformat(),
            "end": detected.isoformat(),
        },
        "after": {
            "start": detected.isoformat(),
            "end": (detected + timedelta(minutes=after_minutes)).isoformat(),
        },
    }


def summarize_ais_window(observations: list[dict], detection_time: str) -> dict:
    window = build_ais_window(detection_time)
    detected = _parse(detection_time)
    before = [o for o in observations if _parse(o["timestamp"]) < detected]
    after = [o for o in observations if _parse(o["timestamp"]) >= detected]

    return {
        "window": window,
        "before_count": len(before),
        "after_count": len(after),
        "before_observations": before,
        "after_observations": after,
        "coverage_status": "OBSERVATIONS_AVAILABLE" if observations else "NO_OBSERVATIONS",
        "interpretation": (
            "AIS absence is not evidence of intentional shutdown; "
            "check provider coverage, receiver availability, and data quality."
        ),
    }
