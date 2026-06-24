import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "scorer" in data["service"]


def test_score_hot_lead():
    resp = client.post("/score", json={
        "company": "Smith Roofing LLC",
        "industry": "roofing",
        "employees": 25,
        "message": "We need lead follow-up automation for our roofing business in DFW area",
        "source": "paid",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] >= 0.75
    assert data["tier"] == "Hot"
    assert "Apollo" in data["route"]


def test_score_warm_lead():
    resp = client.post("/score", json={
        "company": "Generic Corp",
        "industry": "retail",
        "employees": 10,
        "message": "interested",
        "source": "organic",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert 0.45 <= data["score"] < 0.75
    assert data["tier"] == "Warm"


def test_score_cold_lead_with_no_fields():
    resp = client.post("/score", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] < 0.45
    assert data["tier"] == "Cold"
    assert "CRM only" in data["route"]


def test_explanation_values_sum_to_total_score():
    resp = client.post("/score", json={
        "company": "Acme Plumbing",
        "industry": "plumbing",
        "employees": 15,
        "message": "Need automation for 50 leads per week",
        "source": "paid",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert abs(sum(data["explanation"].values()) - data["score"]) < 0.001


def test_no_company_lowers_score():
    resp_with = client.post("/score", json={"company": "TestCo", "industry": "hvac"})
    resp_without = client.post("/score", json={"industry": "hvac"})
    assert resp_with.json()["score"] > resp_without.json()["score"]


def test_paid_source_beats_organic():
    resp_paid = client.post("/score", json={"source": "paid"})
    resp_organic = client.post("/score", json={"source": "organic"})
    assert resp_paid.json()["score"] > resp_organic.json()["score"]


def test_hot_industry_keywords_give_max_industry_score():
    hot_industries = ["roofing", "hvac", "plumbing", "electrical", "landscaping", "construction"]
    for industry in hot_industries:
        resp = client.post("/score", json={"company": "TestCo", "industry": industry})
        assert resp.status_code == 200
        explanation = resp.json()["explanation"]
        assert explanation["industry"] == pytest.approx(0.25 * 1.0), f"Failed for industry: {industry}"


def test_employee_score_caps_at_50_employees():
    resp_50 = client.post("/score", json={"employees": 50})
    resp_200 = client.post("/score", json={"employees": 200})
    assert resp_50.json()["score"] == pytest.approx(resp_200.json()["score"])
