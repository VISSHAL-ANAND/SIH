from datetime import datetime, timezone

import pandas as pd
import pytest

from main.gfw_ais_provider import GFWAPIError, GFWAISProvider


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_gfw_provider_converts_presence_rows(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse(
            payload={
                "entries": [
                    {
                        "public-global-presence:v4.0": [
                            {
                                "date": "2026-09-10 09:00",
                                "entryTimestamp": "2026-09-10T09:03:00Z",
                                "lat": 13.01,
                                "lon": 80.02,
                                "mmsi": "419000001",
                                "shipName": "TEST VESSEL",
                                "flag": "IND",
                                "vesselType": "cargo",
                            }
                        ]
                    }
                ]
            }
        )

    monkeypatch.setattr("main.gfw_ais_provider.requests.post", fake_post)
    provider = GFWAISProvider(token="test-token")
    rows = provider.get_presence(
        [{"lat": 13.0, "lon": 80.0}],
        datetime.now(timezone.utc),
        window_hours=2,
    )

    assert isinstance(rows, pd.DataFrame)
    assert len(rows) == 1
    assert rows.iloc[0]["mmsi"] == "419000001"
    assert rows.iloc[0]["vessel_name"] == "TEST VESSEL"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer test-token"
    assert captured["kwargs"]["params"]["group-by"] == "MMSI"
    assert captured["kwargs"]["params"]["datasets[0]"] == "public-global-presence:latest"


def test_gfw_provider_rejects_old_replay_timestamp(monkeypatch):
    monkeypatch.setattr("main.gfw_ais_provider.datetime", __import__("main.gfw_ais_provider", fromlist=["datetime"]).datetime)
    provider = GFWAISProvider(token="test-token")
    old = datetime(2026, 6, 21, 22, 50)
    with pytest.raises(GFWAPIError, match="only available"):
        provider.get_presence([{"lat": 13.0, "lon": 80.0}], old)


def test_gfw_provider_surfaces_permission_errors(monkeypatch):
    monkeypatch.setattr(
        "main.gfw_ais_provider.requests.post",
        lambda *args, **kwargs: FakeResponse(status_code=403, text="Insufficient permissions"),
    )
    provider = GFWAISProvider(token="test-token")
    with pytest.raises(GFWAPIError, match="permission error"):
        provider.get_presence([{"lat": 13.0, "lon": 80.0}], datetime.now(timezone.utc))
