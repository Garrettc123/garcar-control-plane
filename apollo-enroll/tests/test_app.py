import sys
import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app

client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_enroll_queues_background_task_and_returns_200():
    with patch("app.enroll_lead", return_value=True) as mock_enroll:
        r = client.post(
            "/enroll",
            json={"email": "test@example.com", "name": "Test User", "company": "Acme Roofing", "tier": "hot"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert body["email"] == "test@example.com"


def test_enroll_missing_email_returns_422():
    r = client.post("/enroll", json={"name": "No Email"})
    assert r.status_code == 422


def test_contractor_sequence_routing():
    from enroll import _pick_sequence
    with patch("enroll.APOLLO_SEQ_CONTRACTORS", "seq_contractors_id"):
        seq = _pick_sequence({"industry": "roofing", "utm_campaign": ""})
    assert seq == "seq_contractors_id"


def test_pthch_sequence_routing():
    from enroll import _pick_sequence
    with patch("enroll.APOLLO_SEQ_PTHCH", "seq_pthch_id"):
        seq = _pick_sequence({"industry": "tech", "utm_campaign": "pthch-audit"})
    assert seq == "seq_pthch_id"


def test_agency_sequence_routing():
    from enroll import _pick_sequence
    with patch("enroll.APOLLO_SEQ_AGENCY", "seq_agency_id"):
        seq = _pick_sequence({"industry": "digital marketing", "utm_campaign": ""})
    assert seq == "seq_agency_id"


def test_enroll_lead_noop_without_api_key():
    from enroll import enroll_lead
    with patch("enroll.APOLLO_API_KEY", ""):
        result = enroll_lead({"email": "test@example.com", "name": "Test"})
    assert result is False
