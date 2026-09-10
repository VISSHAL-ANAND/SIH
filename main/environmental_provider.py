"""Environmental providers for auditable IMW drift evidence.

The live provider uses Open-Meteo's Marine API for ocean currents and its
Forecast API for 10 m wind. It returns observations in the component format
expected by ``main.drift_analysis``. Network failure is reported to the caller;
no synthetic fallback values are generated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any

import requests

MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass
class EnvironmentalObservation:
    timestamp: datetime
    latitude: float
    longitude: float
    current_speed_mps: float | None = None
    current_direction_deg: float | None = None
    wind_speed_mps: float | None = None
    wind_direction_deg: float | None = None
    source: str = "UNSPECIFIED"
    quality: str = "UNKNOWN"


class EnvironmentalProvider:
    """Interface for authorized current/wind data providers."""

    def get_observation(self, latitude: float, longitude: float, timestamp: datetime) -> EnvironmentalObservation | None:
        raise NotImplementedError


class StaticEnvironmentalProvider(EnvironmentalProvider):
    """Explicitly supplied observation, useful for integration tests and demos."""

    def __init__(self, observation: EnvironmentalObservation):
        self.observation = observation

    def get_observation(self, latitude: float, longitude: float, timestamp: datetime):
        return self.observation


class OpenMeteoEnvironmentalProvider(EnvironmentalProvider):
    """Fetch real ocean-current and wind observations around a target time."""

    source_name = "Open-Meteo Marine + Forecast API"

    def __init__(self, timeout_seconds: float = 12.0):
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _vector(speed_mps: float, direction_deg: float, *, coming_from: bool = False) -> tuple[float, float]:
        direction = math.radians(float(direction_deg))
        sign = -1.0 if coming_from else 1.0
        return sign * speed_mps * math.sin(direction), sign * speed_mps * math.cos(direction)

    def get_observations(self, latitude: float, longitude: float, timestamp: datetime, window_hours: int = 3) -> list[dict[str, Any]]:
        target = self._utc(timestamp)
        start = (target - timedelta(hours=max(1, window_hours))).date().isoformat()
        end = (target + timedelta(hours=max(1, window_hours))).date().isoformat()
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "ocean_current_velocity,ocean_current_direction",
            "start_date": start,
            "end_date": end,
            "timezone": "UTC",
            "cell_selection": "sea",
        }
        marine = requests.get(MARINE_API_URL, params=params, timeout=self.timeout_seconds)
        marine.raise_for_status()
        marine_data = marine.json()
        if marine_data.get("error"):
            raise RuntimeError(marine_data.get("reason", "Open-Meteo Marine API error"))

        wind_params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "wind_speed_10m,wind_direction_10m",
            "start_date": start,
            "end_date": end,
            "timezone": "UTC",
        }
        weather = requests.get(FORECAST_API_URL, params=wind_params, timeout=self.timeout_seconds)
        weather.raise_for_status()
        weather_data = weather.json()
        if weather_data.get("error"):
            raise RuntimeError(weather_data.get("reason", "Open-Meteo Forecast API error"))

        mh = marine_data.get("hourly", {})
        wh = weather_data.get("hourly", {})
        wind_times = wh.get("time", [])
        wind_by_time = {t: i for i, t in enumerate(wind_times)}
        rows: list[dict[str, Any]] = []
        for i, raw_time in enumerate(mh.get("time", [])):
            if raw_time not in wind_by_time:
                continue
            wi = wind_by_time[raw_time]
            try:
                current_speed_kmh = mh["ocean_current_velocity"][i]
                current_dir = mh["ocean_current_direction"][i]
                wind_speed_kmh = wh["wind_speed_10m"][wi]
                wind_dir = wh["wind_direction_10m"][wi]
                if any(v is None for v in (current_speed_kmh, current_dir, wind_speed_kmh, wind_dir)):
                    continue
                current_speed_mps = float(current_speed_kmh) / 3.6
                wind_speed_mps = float(wind_speed_kmh) / 3.6
                cu, cv = self._vector(current_speed_mps, float(current_dir))
                wu, wv = self._vector(wind_speed_mps, float(wind_dir), coming_from=True)
                rows.append({
                    "timestamp": raw_time + ("Z" if not raw_time.endswith("Z") else ""),
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "current_u_mps": round(cu, 6),
                    "current_v_mps": round(cv, 6),
                    "wind_u_mps": round(wu, 6),
                    "wind_v_mps": round(wv, 6),
                    "current_speed_mps": round(current_speed_mps, 6),
                    "current_direction_deg": float(current_dir),
                    "wind_speed_mps": round(wind_speed_mps, 6),
                    "wind_direction_deg": float(wind_dir),
                    "source": self.source_name,
                    "quality": "MODELLED",
                })
            except (TypeError, ValueError, IndexError):
                continue
        if not rows:
            raise RuntimeError("Open-Meteo returned no usable current/wind observations for the requested time window")
        return rows

    def get_observation(self, latitude: float, longitude: float, timestamp: datetime) -> EnvironmentalObservation | None:
        rows = self.get_observations(latitude, longitude, timestamp, window_hours=1)
        target = self._utc(timestamp)
        row = min(rows, key=lambda item: abs(datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")) - target))
        return EnvironmentalObservation(
            timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
            latitude=latitude,
            longitude=longitude,
            current_speed_mps=row["current_speed_mps"],
            current_direction_deg=row["current_direction_deg"],
            wind_speed_mps=row["wind_speed_mps"],
            wind_direction_deg=row["wind_direction_deg"],
            source=row["source"],
            quality=row["quality"],
        )
