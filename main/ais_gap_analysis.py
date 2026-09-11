"""Coverage-aware AIS gap analysis for IMW investigations.

A missing AIS observation is treated as an observed data gap, never as proof of
intentional AIS shutdown, spoofing, or vessel responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd


@dataclass
class AISGapAnalysis:
    mmsi: str
    detection_time: datetime
    coverage_status: str
    status: str
    pre_event_gap_minutes: float | None
    post_event_gap_minutes: float | None
    largest_internal_gap_minutes: float | None
    observations_before: int
    observations_after: int
    expected_interval_minutes: float
    evidence_strength: float
    reason: str


def _normalize_timestamp(value) -> pd.Timestamp | None:
    try:
        ts = pd.Timestamp(value)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts
    except (TypeError, ValueError):
        return None


def analyze_ais_gaps(
    ais_df: pd.DataFrame,
    mmsi: str,
    detection_time: datetime,
    *,
    lookback_hours: float = 12.0,
    lookahead_hours: float = 12.0,
    expected_interval_minutes: float = 15.0,
    gap_multiplier: float = 2.0,
    coverage_available: bool | None = None,
) -> AISGapAnalysis:
    """Classify observed AIS gaps around a SAR event.

    ``coverage_available`` describes whether the AIS source is known to cover
    the area/time being investigated. If it is unknown, gaps are explicitly
    marked as requiring coverage review rather than interpreted as darkness.
    """
    detection = _normalize_timestamp(detection_time)
    if detection is None:
        detection = pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
    detection_dt = detection.to_pydatetime()

    expected = max(0.1, float(expected_interval_minutes))
    threshold = expected * max(1.0, float(gap_multiplier))

    required = {"mmsi", "timestamp", "lat", "lon"}
    if ais_df is None or ais_df.empty or not required.issubset(ais_df.columns):
        coverage = "COVERAGE_UNAVAILABLE" if coverage_available is False else "COVERAGE_UNKNOWN"
        return AISGapAnalysis(
            mmsi=str(mmsi), detection_time=detection_dt,
            coverage_status=coverage, status="INSUFFICIENT_DATA",
            pre_event_gap_minutes=None, post_event_gap_minutes=None,
            largest_internal_gap_minutes=None, observations_before=0,
            observations_after=0, expected_interval_minutes=expected,
            evidence_strength=0.0,
            reason="The supplied AIS feed does not contain enough usable fields to assess gaps.",
        )

    vessel = ais_df[ais_df["mmsi"].astype(str) == str(mmsi)].copy()
    vessel["timestamp"] = vessel["timestamp"].map(_normalize_timestamp)
    vessel = vessel.dropna(subset=["timestamp"]).sort_values("timestamp")

    start = detection - timedelta(hours=float(lookback_hours))
    end = detection + timedelta(hours=float(lookahead_hours))
    vessel = vessel[(vessel["timestamp"] >= start) & (vessel["timestamp"] <= end)]

    before = vessel[vessel["timestamp"] < detection]
    after = vessel[vessel["timestamp"] >= detection]

    coverage = (
        "COVERAGE_CONFIRMED"
        if coverage_available is True
        else "COVERAGE_UNAVAILABLE"
        if coverage_available is False
        else "COVERAGE_UNKNOWN"
    )

    if vessel.empty:
        return AISGapAnalysis(
            mmsi=str(mmsi), detection_time=detection_dt,
            coverage_status=coverage, status="NO_OBSERVATIONS",
            pre_event_gap_minutes=None, post_event_gap_minutes=None,
            largest_internal_gap_minutes=None, observations_before=0,
            observations_after=0, expected_interval_minutes=expected,
            evidence_strength=0.0,
            reason="No AIS observations for this MMSI were supplied in the investigation window; coverage must be verified before interpreting the absence.",
        )

    pre_gap = None
    post_gap = None
    if not before.empty:
        pre_gap = max(0.0, (detection - before["timestamp"].iloc[-1]).total_seconds() / 60.0)
    if not after.empty:
        post_gap = max(0.0, (after["timestamp"].iloc[0] - detection).total_seconds() / 60.0)

    internal_gap = None
    if len(vessel) >= 2:
        deltas = vessel["timestamp"].diff().dt.total_seconds().div(60.0).dropna()
        if not deltas.empty:
            internal_gap = float(deltas.max())

    significant_pre = pre_gap is not None and pre_gap > threshold
    significant_post = post_gap is not None and post_gap > threshold
    significant_internal = internal_gap is not None and internal_gap > threshold

    if coverage_available is False:
        status = "NO_COVERAGE_TO_ASSESS"
        strength = 0.0
        reason = "The AIS source is marked unavailable for this investigation area/time, so absence cannot be classified as a vessel gap."
    elif significant_pre or significant_post or significant_internal:
        if coverage_available is True:
            status = "AIS_GAP_OBSERVED"
            strength = 0.65
            reason = "A time interval exceeds the configured expected AIS observation interval while source coverage is confirmed; this remains a data-gap observation, not proof of intentional shutdown."
        else:
            status = "GAP_REQUIRES_COVERAGE_REVIEW"
            strength = 0.35
            reason = "A time interval exceeds the configured expected AIS observation interval, but source coverage is not confirmed; the gap does not establish intentional shutdown or responsibility, so review provider/receiver coverage before interpretation."
    else:
        status = "AIS_CONTINUITY_OBSERVED"
        strength = 0.9 if coverage_available is True else 0.75
        reason = "AIS observations remain within the configured expected interval around the event; no significant observed gap was detected."

    return AISGapAnalysis(
        mmsi=str(mmsi), detection_time=detection_dt,
        coverage_status=coverage, status=status,
        pre_event_gap_minutes=round(pre_gap, 2) if pre_gap is not None else None,
        post_event_gap_minutes=round(post_gap, 2) if post_gap is not None else None,
        largest_internal_gap_minutes=round(internal_gap, 2) if internal_gap is not None else None,
        observations_before=len(before), observations_after=len(after),
        expected_interval_minutes=expected,
        evidence_strength=round(strength, 3), reason=reason,
    )


def gap_analysis_to_dict(result: AISGapAnalysis) -> dict:
    return {
        "mmsi": result.mmsi,
        "detection_time": result.detection_time.isoformat(),
        "coverage_status": result.coverage_status,
        "status": result.status,
        "pre_event_gap_minutes": result.pre_event_gap_minutes,
        "post_event_gap_minutes": result.post_event_gap_minutes,
        "largest_internal_gap_minutes": result.largest_internal_gap_minutes,
        "observations_before": result.observations_before,
        "observations_after": result.observations_after,
        "expected_interval_minutes": result.expected_interval_minutes,
        "evidence_strength": result.evidence_strength,
        "responsibility_status": "NOT_ESTABLISHED",
        "interpretation": "AIS gap evidence does not establish intentional shutdown, spoofing, or responsibility.",
        "reason": result.reason,
    }
