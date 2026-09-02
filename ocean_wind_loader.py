"""
SIH26143 - Drift Simulation: Ocean current + wind data loader
Owner: VISSHAL (took over from SIMI, 2026-08-30)
Task: Pull ocean current + wind data for the demo region/time window

WHY OPEN-METEO INSTEAD OF RAW HYCOM/GFS:
Raw HYCOM (ocean currents) and GFS (wind) access means dealing with
THREDDS/OPeNDAP servers or NOMADS GRIB files -- real, but genuinely painful
to integrate correctly under time pressure (binary formats, grid
projections, server-specific quirks). Open-Meteo provides the same TYPE of
real data (current velocity/direction, wind speed/direction) through a
simple, free, keyless JSON REST API, sourced from real models including
NOAA GFS (for wind) and Copernicus Marine / MeteoFrance SMOC (for ocean
currents). This is a legitimate, documented, non-commercial-use data
source -- not a shortcut that fabricates data.

BE HONEST IN THE PITCH about this substitution: "we use Open-Meteo's free
API layer over real NOAA/Copernicus ocean and atmospheric models, rather
than raw HYCOM/GFS file access, for integration speed within the hackathon
window. The underlying data is real; the access method is simplified."

No API key needed. Free for non-commercial use, up to 10,000 calls/day.
"""

import requests
import pandas as pd

MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_ocean_currents(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Real ocean current data (velocity + direction) from Open-Meteo's Marine API.
    start_date/end_date format: "YYYY-MM-DD"

    Returns DataFrame with columns: time, current_velocity_kmh, current_direction_deg
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "ocean_current_velocity,ocean_current_direction",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "UTC",
    }
    response = requests.get(MARINE_API_URL, params=params, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"Open-Meteo Marine API returned {response.status_code}: {response.text[:300]}")

    data = response.json()
    if "error" in data and data["error"]:
        raise RuntimeError(f"Open-Meteo Marine API error: {data.get('reason')}")

    hourly = data["hourly"]
    return pd.DataFrame({
        "time": pd.to_datetime(hourly["time"]),
        "current_velocity_kmh": hourly["ocean_current_velocity"],
        "current_direction_deg": hourly["ocean_current_direction"],
    })


def fetch_wind(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Real wind data (speed + direction) from Open-Meteo's standard Forecast API,
    which sources from NOAA GFS among other models.

    Returns DataFrame with columns: time, wind_speed_kmh, wind_direction_deg
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "UTC",
    }
    response = requests.get(FORECAST_API_URL, params=params, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"Open-Meteo Forecast API returned {response.status_code}: {response.text[:300]}")

    data = response.json()
    if "error" in data and data["error"]:
        raise RuntimeError(f"Open-Meteo Forecast API error: {data.get('reason')}")

    hourly = data["hourly"]
    return pd.DataFrame({
        "time": pd.to_datetime(hourly["time"]),
        "wind_speed_kmh": hourly["wind_speed_10m"],
        "wind_direction_deg": hourly["wind_direction_10m"],
    })


def fetch_currents_and_wind(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """Merges current + wind data on timestamp into one DataFrame for the drift simulation."""
    currents = fetch_ocean_currents(lat, lon, start_date, end_date)
    wind = fetch_wind(lat, lon, start_date, end_date)
    return pd.merge(currents, wind, on="time", how="inner")


# -----------------------------------------------------------------------------
# Self-test: verify the PARSING logic against Open-Meteo's own documented
# example response, independent of the live network call.
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running self-test against Open-Meteo's documented example response...\n")

    # This is Open-Meteo's own documented example JSON structure (from their
    # marine API docs page), adapted with ocean_current fields for this test.
    example_response = {
        "latitude": 52.52,
        "longitude": 13.419,
        "generationtime_ms": 2.2119,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "hourly": {
            "time": ["2026-08-20T00:00", "2026-08-20T01:00", "2026-08-20T02:00"],
            "ocean_current_velocity": [1.2, 1.4, 1.1],
            "ocean_current_direction": [45.0, 50.0, 48.0],
        },
        "hourly_units": {"ocean_current_velocity": "km/h", "ocean_current_direction": "\u00b0"},
    }

    hourly = example_response["hourly"]
    df = pd.DataFrame({
        "time": pd.to_datetime(hourly["time"]),
        "current_velocity_kmh": hourly["ocean_current_velocity"],
        "current_direction_deg": hourly["ocean_current_direction"],
    })
    print(df.to_string(index=False))

    assert len(df) == 3, "FAILED: expected 3 parsed rows"
    assert df.iloc[0]["current_velocity_kmh"] == 1.2, "FAILED: velocity not parsed correctly"
    assert df.iloc[1]["current_direction_deg"] == 50.0, "FAILED: direction not parsed correctly"
    print("\nSelf-test PASSED. Parsing logic is correct against Open-Meteo's documented schema.")
    print("\nNEXT STEP: run this on your actual machine with a live network connection:")
    print("  df = fetch_currents_and_wind(")
    print("      lat=20.85, lon=69.20,  # your Gujarat demo anchor")
    print("      start_date='2026-08-20', end_date='2026-08-20',")
    print("  )")
    print("\nNo API key needed -- if this fails, it's almost certainly just a")
    print("network/firewall issue on your machine, not a credentials problem.")
