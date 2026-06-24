import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from main import app, maut_score

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_webhook_verify_success():
    os.environ["META_VERIFY_TOKEN"] = "test-token"
    import importlib, main as m
    m.META_VERIFY_TOKEN = "test-token"
    r = client.get("/?hub.mode=subscribe&hub.verify_token=test-token&hub.challenge=abc123")
    assert r.status_code == 200
    assert r.text == "abc123"


def test_webhook_verify_failure():
    r = client.get("/?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=abc123")
    assert r.status_code == 403


def test_maut_score_hot_lead():
    lead = {
        "company": "DFW Roofing Co",
        "industry": "roofing",
        "employees": "30",
        "message": "Looking for AI-powered lead gen system for our roofing business we need something fast today",
        "source": "paid",
    }
    score = maut_score(lead)
    assert score >= 0.75, f"Expected hot lead score >= 0.75, got {score}"


def test_maut_score_cold_lead():
    lead = {
        "company": "",
        "industry": "retail",
        "employees": "0",
        "message": "",
        "source": "organic",
    }
    score = maut_score(lead)
    assert score < 0.45, f"Expected cold lead score < 0.45, got {score}"


def test_maut_score_warm_lead():
    lead = {
        "company": "HVAC Pro LLC",
        "industry": "hvac",
        "employees": "5",
        "message": "Interested",
        "source": "organic",
    }
    score = maut_score(lead)
    assert 0.45 <= score < 0.75, f"Expected warm lead score 0.45-0.75, got {score}"


def test_webhook_event_processes_lead():
    payload = {
        "entry": [{
            "changes": [{
                "field": "leadgen",
                "value": {
                    "field_data": [
                        {"name": "full_name", "values": ["John Roofer"]},
                        {"name": "email", "values": ["john@dfwroofing.example.com"]},
                        {"name": "company_name", "values": ["DFW Roofing"]},
                        {"name": "industry", "values": ["roofing"]},
                        {"name": "employees", "values": ["25"]},
                        {"name": "message", "values": ["We need a full lead gen overhaul for our roofing company"]},
                    ]
                }
            }]
        }]
    }
    with patch("main.save_to_notion") as mock_notion, patch("main.notify_slack") as mock_slack:
        r = client.post("/", json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    mock_notion.assert_called_once()
    mock_slack.assert_called_once()


def test_webhook_event_ignores_non_leadgen():
    payload = {
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {}
            }]
        }]
    }
    with patch("main.save_to_notion") as mock_notion:
        r = client.post("/", json=payload)
    assert r.status_code == 200
    mock_notion.assert_not_called()
