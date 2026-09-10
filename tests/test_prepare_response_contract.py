import pytest
from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_prepare_response_contract_is_draft_only():
    response = client.post('/api/prepare-response', json={
        'incident_id': 'IMW-CONTRACT-001',
        'slick_centroid': [12.3, 74.5],
        'spill_area_sq_m': 1250.0,
        'suspect_vessel': {'mmsi': '123456789', 'vessel_name': 'TEST'},
        'threat_score': 0.81,
        'evidence_summary': 'AIS correlation available',
    })
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'DRAFT_REQUIRES_OPERATOR_CONFIRMATION'
    assert body['operator_confirmation']['required'] is True
    assert body['operator_confirmation']['confirmed'] is False
    assert body['transmission']['status'] == 'NOT_SENT'
    assert body['payload_preview']['incident_id'] == 'IMW-CONTRACT-001'


def test_prepare_response_rejects_missing_required_fields():
    response = client.post('/api/prepare-response', json={'incident_id': 'IMW-BAD'})
    assert response.status_code == 422
