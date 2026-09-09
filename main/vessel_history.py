"""AIS vessel-history analysis for IMW.

This module does not infer intentional AIS shutdown. It measures the observed
broadcast continuity of a candidate MMSI before/after a SAR detection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from .ais_matcher import haversine_km


@dataclass
class VesselHistoryResult:
    mmsi: str
    vessel_name: str | None
    last_before_time: datetime | None
    last_before_distance_km: float | None
    first_after_time: datetime | None
    first_after_distance_km: float | None
    gap_minutes: float | None
    broadcasts_before: int
    broadcasts_after: int
    status: str
    evidence_strength: float
    reason: str


def analyze_vessel_history(
    ais_df: pd.DataFrame,
    mmsi: str,
    hull_lat: float,
    hull_lon: float,
    detection_time: datetime,
    lookback_hours: float = 12.0,
    lookahead_hours: float = 12.0,
    proximity_km: float = 25.0,
) -> VesselHistoryResult:
    """Measure a candidate vessel's observed AIS continuity around detection."""
    vessel = ais_df[ais_df["mmsi"].astype(str) == str(mmsi)].copy()
    if vessel.empty:
        return VesselHistoryResult(
            mmsi=str(mmsi), vessel_name=None, last_before_time=None,
            last_before_distance_km=None, first_after_time=None,
            first_after_distance_km=None, gap_minutes=None,
            broadcasts_before=0, broadcasts_after=0,
            status="NO_VESSEL_HISTORY", evidence_strength=0.0,
            reason="No historical AIS records for this MMSI in the supplied dataset.",
        )

    vessel["timestamp"] = pd.to_datetime(vessel["timestamp"], errors="coerce").dt.tz_localize(None)
    detection_time = detection_time.replace(tzinfo=None)
    vessel = vessel.dropna(subset=["timestamp"]).sort_values("timestamp")

    before = vessel[
        (vessel["timestamp"] <= detection_time)
        & (vessel["timestamp"] >= detection_time - timedelta(hours=lookback_hours))
    ].copy()
    after = vessel[
        (vessel["timestamp"] >= detection_time)
        & (vessel["timestamp"] <= detection_time + timedelta(hours=lookahead_hours))
    ].copy()

    def distance(frame):
        if frame.empty:
            return None
        row = frame.iloc[-1]
        return float(haversine_km(hull_lat, hull_lon, row["lat"], row["lon"]))

    last_before = before.iloc[-1] if not before.empty else None
    first_after = after.iloc[0] if not after.empty else None

    gap_minutes = None
    if last_before is not None and first_after is not None:
        gap_minutes = max(0.0, (first_after["timestamp"] - last_before["timestamp"]).total_seconds() / 60.0)

    if before.empty and after.empty:
        status = "NO_HISTORY_AROUND_EVENT"
        strength = 0.0
        reason = "The supplied AIS dataset contains no records for this vessel around the SAR event."
    elif first_after is not None and last_before is not None:
        status = "CONTINUITY_OBSERVED"
        strength = 0.9 if (gap_minutes or 0) <= 30 else max(0.2, 1.0 - (gap_minutes or 0) / 360.0)
        reason = "The candidate vessel has AIS observations on both sides of the SAR event."
    elif last_before is not None:
        status = "POST_EVENT_GAP_UNRESOLVED"
        strength = 0.25
        reason = "AIS was observed before the event, but no later broadcast is present in the supplied lookahead window; coverage limits must be checked."
    else:
        status = "PRE_EVENT_HISTORY_ONLY"
        strength = 0.15
        reason = "AIS appears after the event but there is no pre-event history in the supplied window."

    name = last_before.get("vessel_name") if last_before is not None else (
        first_after.get("vessel_name") if first_after is not None else None
    )
    if pd.isna(name):
        name = None

    return VesselHistoryResult(
        mmsi=str(mmsi),
        vessel_name=str(name) if name else None,
        last_before_time=last_before["timestamp"].to_pydatetime() if last_before is not None else None,
        last_before_distance_km=distance(before),
        first_after_time=first_after["timestamp"].to_pydatetime() if first_after is not None else None,
        first_after_distance_km=distance(after),
        gap_minutes=gap_minutes,
        broadcasts_before=len(before),
        broadcasts_after=len(after),
        status=status,
        evidence_strength=round(float(strength), 3),
        reason=reason,
    )


def history_to_dict(result: VesselHistoryResult) -> dict:
    return {
        "mmsi": result.mmsi,
        "vessel_name": result.vessel_name,
        "last_before_time": result.last_before_time.isoformat() if result.last_before_time else None,
        "last_before_distance_km": result.last_before_distance_km,
        "first_after_time": result.first_after_time.isoformat() if result.first_after_time else None,
        "first_after_distance_km": result.first_after_distance_km,
        "gap_minutes": result.gap_minutes,
        "broadcasts_before": result.broadcasts_before,
        "broadcasts_after": result.broadcasts_after,
        "status": result.status,
        "evidence_strength": result.evidence_strength,
        "reason": result.reason,
    }
