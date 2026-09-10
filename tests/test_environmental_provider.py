from datetime import datetime, timezone

from main.environmental_provider import OpenMeteoEnvironmentalProvider


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_open_meteo_provider_converts_current_and_wind_to_components(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        if "marine-api" in url:
            return FakeResponse({
                "hourly": {
                    "time": ["2026-09-10T12:00", "2026-09-10T13:00"],
                    "ocean_current_velocity": [3.6, 7.2],
                    "ocean_current_direction": [90.0, 0.0],
                }
            })
        return FakeResponse({
            "hourly": {
                "time": ["2026-09-10T12:00", "2026-09-10T13:00"],
                "wind_speed_10m": [3.6, 3.6],
                "wind_direction_10m": [90.0, 180.0],
            }
        })

    monkeypatch.setattr("main.environmental_provider.requests.get", fake_get)
    provider = OpenMeteoEnvironmentalProvider()
    rows = provider.get_observations(10.0, 80.0, datetime(2026, 9, 10, 13, 0, tzinfo=timezone.utc))

    assert len(rows) == 2
    assert rows[0]["source"] == "Open-Meteo Marine + Forecast API"
    assert rows[0]["quality"] == "MODELLED"
    assert abs(rows[0]["current_u_mps"] - 1.0) < 1e-6
    assert abs(rows[0]["current_v_mps"]) < 1e-6
    assert abs(rows[0]["wind_u_mps"] + 1.0) < 1e-6
    assert abs(rows[0]["wind_v_mps"]) < 1e-6
    assert len(calls) == 2
    assert "historical-forecast-api" not in calls[1][0]


def test_historical_sar_replay_uses_historical_forecast_wind(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append(url)
        if "marine-api" in url:
            return FakeResponse({
                "hourly": {
                    "time": ["2026-06-21T22:00"],
                    "ocean_current_velocity": [3.6],
                    "ocean_current_direction": [90.0],
                }
            })
        return FakeResponse({
            "hourly": {
                "time": ["2026-06-21T22:00"],
                "wind_speed_10m": [3.6],
                "wind_direction_10m": [90.0],
            }
        })

    monkeypatch.setattr("main.environmental_provider.requests.get", fake_get)
    provider = OpenMeteoEnvironmentalProvider()
    rows = provider.get_observations(10.0, 80.0, datetime(2026, 6, 21, 22, 0, tzinfo=timezone.utc))

    assert len(rows) == 1
    assert "historical-forecast-api" in calls[1]
    assert rows[0]["source"] == "Open-Meteo Marine + Historical Forecast API"


def test_provider_raises_when_no_usable_rows(monkeypatch):
    def fake_get(url, params, timeout):
        if "marine-api" in url:
            return FakeResponse({"hourly": {"time": [], "ocean_current_velocity": [], "ocean_current_direction": []}})
        return FakeResponse({"hourly": {"time": [], "wind_speed_10m": [], "wind_direction_10m": []}})

    monkeypatch.setattr("main.environmental_provider.requests.get", fake_get)
    provider = OpenMeteoEnvironmentalProvider()

    try:
        provider.get_observations(10.0, 80.0, datetime(2026, 6, 21, 23, 0, tzinfo=timezone.utc))
    except RuntimeError as exc:
        assert "no usable" in str(exc).lower()
    else:
        raise AssertionError("Expected RuntimeError when the provider returns no usable rows")
