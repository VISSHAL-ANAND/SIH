"""Global Fishing Watch AIS-presence adapter for IMW.

The adapter is opt-in through ``GFW_API_ACCESS_TOKEN``. It queries the GFW
4Wings AIS vessel-presence dataset for a small custom polygon around the SAR
hulls and converts the hourly, gridded presence records into the internal AIS
schema used by candidate matching.

GFW data is real external evidence, not synthetic AIS. The provider raises an
explicit error for missing credentials, permission failures, unsupported
historical dates, or malformed responses so callers can choose an explicit
fallback and label it correctly.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd
import requests

GFW_API_BASE = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
GFW_DATASET = "public-global-presence:latest"
GFW_MAX_AGE_HOURS = 96


class GFWAPIError(RuntimeError):
    """Raised when GFW cannot provide usable AIS presence evidence."""


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _polygon_for_hulls(hulls: Iterable[dict], radius_km: float = 30.0) -> dict:
    points = [(float(h["lat"]), float(h["lon"])) for h in hulls if h.get("lat") is not None and h.get("lon") is not None]
    if not points:
        raise GFWAPIError("No georeferenced SAR hulls are available for the GFW query.")

    min_lat = min(p[0] for p in points)
    max_lat = max(p[0] for p in points)
    min_lon = min(p[1] for p in points)
    max_lon = max(p[1] for p in points)

    lat_pad = radius_km / 111.32
    mean_lat = max(1.0, min(89.0, sum(p[0] for p in points) / len(points)))
    lon_pad = radius_km / (111.32 * math.cos(math.radians(mean_lat)))

    min_lat, max_lat = max(-89.9, min_lat - lat_pad), min(89.9, max_lat + lat_pad)
    min_lon, max_lon = max(-179.9, min_lon - lon_pad), min(179.9, max_lon + lon_pad)

    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]],
    }


class GFWAISProvider:
    """Retrieve real GFW AIS vessel-presence records around SAR hulls."""

    def __init__(self, token: str | None = None, timeout_seconds: int = 30):
        self.token = token or os.getenv("GFW_API_ACCESS_TOKEN")
        self.timeout_seconds = timeout_seconds
        if not self.token:
            raise GFWAPIError("GFW_API_ACCESS_TOKEN is not configured.")

    def get_presence(self, hulls: list[dict], detection_time: datetime, window_hours: float = 2.0) -> pd.DataFrame:
        detection_utc = _parse_timestamp(detection_time.isoformat())
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        age_hours = (now_utc - detection_utc).total_seconds() / 3600.0
        if age_hours > GFW_MAX_AGE_HOURS:
            raise GFWAPIError(
                f"GFW AIS presence is only available to approximately {GFW_MAX_AGE_HOURS} hours before now; "
                f"requested scene is {age_hours:.1f} hours old."
            )
        if age_hours < -1:
            raise GFWAPIError("SAR detection timestamp is in the future relative to the GFW service clock.")

        start = detection_utc - timedelta(hours=window_hours)
        end = detection_utc + timedelta(hours=window_hours)
        polygon = _polygon_for_hulls(hulls)

        params = {
            "spatial-resolution": "HIGH",
            "temporal-resolution": "HOURLY",
            "group-by": "MMSI",
            "datasets[0]": GFW_DATASET,
            "date-range": f"{start.isoformat()}Z,{end.isoformat()}Z",
            "format": "JSON",
            "spatial-aggregation": "false",
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {"geojson": json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": polygon}]})}

        try:
            response = requests.post(
                GFW_API_BASE,
                params=params,
                headers=headers,
                json=body,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise GFWAPIError(f"GFW request failed: {type(exc).__name__}: {exc}") from exc

        if response.status_code in {401, 403}:
            raise GFWAPIError(
                f"GFW authentication/permission error ({response.status_code}). "
                "Check GFW_API_ACCESS_TOKEN and dataset access."
            )
        if response.status_code >= 400:
            detail = response.text[:300].replace("\n", " ")
            raise GFWAPIError(f"GFW API returned HTTP {response.status_code}: {detail}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise GFWAPIError("GFW API returned a non-JSON response.") from exc

        return self._to_dataframe(payload)

    @staticmethod
    def _to_dataframe(payload: dict) -> pd.DataFrame:
        rows: list[dict] = []
        entries = payload.get("entries") or []
        if not isinstance(entries, list):
            raise GFWAPIError("GFW response has an invalid entries field.")

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for dataset_rows in entry.values():
                if not isinstance(dataset_rows, list):
                    continue
                for item in dataset_rows:
                    if not isinstance(item, dict):
                        continue
                    mmsi = item.get("mmsi")
                    lat, lon = item.get("lat"), item.get("lon")
                    if not mmsi or lat is None or lon is None:
                        continue
                    timestamp = item.get("entryTimestamp") or item.get("date")
                    if not timestamp:
                        continue
                    try:
                        ts = _parse_timestamp(timestamp)
                        lat_f, lon_f = float(lat), float(lon)
                    except (TypeError, ValueError):
                        continue
                    rows.append({
                        "mmsi": str(mmsi),
                        "timestamp": ts,
                        "lat": lat_f,
                        "lon": lon_f,
                        "vessel_name": item.get("shipName"),
                        "imo": item.get("imo"),
                        "flag": item.get("flag"),
                        "vessel_type": item.get("vesselType"),
                        "source": "GLOBAL_FISHING_WATCH_AIS_PRESENCE",
                    })

        columns = ["mmsi", "timestamp", "lat", "lon", "vessel_name", "imo", "flag", "vessel_type", "source"]
        return pd.DataFrame(rows, columns=columns)
