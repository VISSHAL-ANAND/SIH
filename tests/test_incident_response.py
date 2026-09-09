from main.incident_response import build_response_draft


def test_response_is_draft_and_not_transmitted():
    incident = {
        "incident_id": "IMW-001",
        "detection": {"timestamp": "2026-01-01T12:00:00+00:00"},
        "geolocation": {"hulls": [{"lat": 12.3, "lon": 74.5}]},
        "spill": {"count": 1},
        "candidates": [{"mmsi": "123", "vessel_name": "TEST", "classification": "POSSIBLE"}],
        "limitations": ["AIS coverage requires review"],
    }
    result = build_response_draft(incident, urgency="HIGH")
    assert result["status"] == "DRAFT_REQUIRES_OPERATOR_CONFIRMATION"
    assert result["operator_confirmation"]["required"] is True
    assert result["operator_confirmation"]["confirmed"] is False
    assert result["transmission"]["status"] == "NOT_SENT"
    assert result["summary"]["primary_location"]["lat"] == 12.3


def test_invalid_urgency_falls_back_to_review():
    result = build_response_draft({}, urgency="SEND_NOW")
    assert result["urgency"] == "REVIEW"
