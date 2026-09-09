"""Provider-neutral environmental observations for IMW drift modeling."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
