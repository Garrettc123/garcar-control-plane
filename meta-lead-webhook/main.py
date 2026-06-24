"""
Meta Lead Webhook — receives Facebook/Instagram lead gen form submissions.
Verifies Meta webhook challenge, scores leads via MAUT, routes to Notion CRM + Slack.
"""
import os
import json
import hashlib
import hmac
import datetime
import urllib.request
import urllib.error
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse

app = FastAPI(title="Garcar Meta Lead Webhook")

META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "garcar-lead-verify-2026")
META_APP_SECRET   = os.environ.get("META_APP_SECRET", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
NOTION_API_KEY    = os.environ.get("NOTION_API_KEY", "")
NOTION_LEADS_DB   = os.environ.get("NOTION_LEADS_DB_ID", "")

HOT_INDUSTRIES = {"construction", "roofing", "hvac", "plumbing", "electrical", "landscaping", "contracting"}

MAUT_WEIGHTS = {
    "company":  0.30,
    "industry": 0.25,
    "employees": 0.20,
    "message": 0.15,
    "source": 0.10,
}


def maut_score(lead: dict) -> float:
    company_score  = 1.0 if lead.get("company") else 0.0
    industry       = (lead.get("industry") or "").lower()
    industry_score = 1.0 if any(h in industry for h in HOT_INDUSTRIES) else 0.4
    employees      = int(lead.get("employees") or 0)
    employee_score = min(employees / 50, 1.0)
    message_score  = min(len(lead.get("message") or "") / 100, 1.0)
    source_score   = 1.0 if lead.get("source") == "paid" else 0.5

    return (
        MAUT_WEIGHTS["company"]   * company_score
        + MAUT_WEIGHTS["industry"]  * industry_score
        + MAUT_WEIGHTS["employees"] * employee_score
        + MAUT_WEIGHTS["message"]   * message_score
        + MAUT_WEIGHTS["source"]    * source_score
    )


def verify_meta_signature(body: bytes, sig_header: str) -> bool:
    if not META_APP_SECRET or not sig_header:
        return True
    try:
        _, sig = sig_header.split("=", 1)
        expected = hmac.new(META_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False


def post_json(url: str, data: dict, headers: dict = None):
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[warn] POST {url} -> {e.code}: {e.read().decode()[:200]}")
        return None


def save_to_notion(lead: dict, score: float):
    if not NOTION_API_KEY or not NOTION_LEADS_DB:
        return
    tier = "Hot" if score >= 0.75 else "Warm" if score >= 0.45 else "Cold"
    post_json(
        "https://api.notion.com/v1/pages",
        {
            "parent": {"database_id": NOTION_LEADS_DB},
            "properties": {
                "Name":    {"title": [{"text": {"content": lead.get("name", "Unknown")}}]},
                "Company": {"rich_text": [{"text": {"content": lead.get("company", "")}}]},
                "Email":   {"email": lead.get("email", "")},
                "Phone":   {"phone_number": lead.get("phone", "")},
                "Score":   {"number": round(score, 3)},
                "Tier":    {"select": {"name": tier}},
                "Source":  {"select": {"name": "Meta"}},
                "Status":  {"select": {"name": "New"}},
                "Created": {"date": {"start": datetime.date.today().isoformat()}},
            },
        },
        {"Authorization": f"Bearer {NOTION_API_KEY}", "Notion-Version": "2022-06-28"},
    )


def notify_slack(lead: dict, score: float):
    if not SLACK_WEBHOOK_URL:
        return
    tier = "HOT" if score >= 0.75 else "WARM" if score >= 0.45 else "cold"
    emoji = ":fire:" if score >= 0.75 else ":thermometer:" if score >= 0.45 else ":snowflake:"
    post_json(
        SLACK_WEBHOOK_URL,
        {"text": (
            f"{emoji} *New {tier} Meta Lead* — score {score:.2f}\n"
            f"Name: {lead.get('name', 'N/A')}  |  Company: {lead.get('company', 'N/A')}\n"
            f"Email: {lead.get('email', 'N/A')}  |  Phone: {lead.get('phone', 'N/A')}\n"
            f"Industry: {lead.get('industry', 'N/A')}  |  Employees: {lead.get('employees', 'N/A')}"
        )},
    )


@app.get("/")
async def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/")
async def webhook_event(request: Request):
    body = await request.body()
    sig = request.headers.get("x-hub-signature-256", "")
    if not verify_meta_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            value = change.get("value", {})
            field_data = {f["name"]: f.get("values", [""])[0] for f in value.get("field_data", [])}
            lead = {
                "name":      field_data.get("full_name", field_data.get("name", "")),
                "email":     field_data.get("email", ""),
                "phone":     field_data.get("phone_number", ""),
                "company":   field_data.get("company_name", ""),
                "industry":  field_data.get("industry", ""),
                "employees": field_data.get("employees", "0"),
                "message":   field_data.get("message", ""),
                "source":    "paid",
            }
            score = maut_score(lead)
            save_to_notion(lead, score)
            if score >= 0.45:
                notify_slack(lead, score)
            print(f"[webhook] lead={lead.get('email')} score={score:.3f}")

    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "meta-lead-webhook"}
