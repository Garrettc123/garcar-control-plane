import os
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import httpx

app = FastAPI(title="Garcar Lead Scorer", version="1.0.0")

APOLLO_ENROLL_URL = os.environ.get("APOLLO_ENROLL_URL", "")

HOT_INDUSTRIES = {
    "construction", "roofing", "hvac", "plumbing",
    "electrical", "landscaping", "contracting",
}

MAUT_WEIGHTS = {
    "company":   0.30,
    "industry":  0.25,
    "employees": 0.20,
    "message":   0.15,
    "source":    0.10,
}


class LeadInput(BaseModel):
    name:         Optional[str] = None
    email:        Optional[str] = None
    company:      Optional[str] = None
    industry:     Optional[str] = None
    employees:    Optional[int] = 0
    message:      Optional[str] = None
    source:       Optional[str] = "organic"
    utm_campaign: Optional[str] = None


class LeadScore(BaseModel):
    score:       float
    tier:        str
    route:       str
    explanation: dict


async def _fire_apollo_enroll(lead: LeadInput, tier: str) -> None:
    if not APOLLO_ENROLL_URL or not lead.email:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{APOLLO_ENROLL_URL}/enroll",
                json={
                    "name":         lead.name,
                    "email":        lead.email,
                    "company":      lead.company,
                    "industry":     lead.industry,
                    "tier":         tier,
                    "utm_campaign": lead.utm_campaign,
                },
            )
    except Exception as exc:
        print(f"[apollo-enroll] fire failed for {lead.email}: {exc}")


@app.post("/score", response_model=LeadScore)
async def score_lead(lead: LeadInput, background_tasks: BackgroundTasks) -> LeadScore:
    company_score  = 1.0 if lead.company else 0.0
    industry       = (lead.industry or "").lower()
    industry_score = 1.0 if any(h in industry for h in HOT_INDUSTRIES) else 0.4
    employee_score = min((lead.employees or 0) / 50, 1.0)
    message_score  = min(len(lead.message or "") / 100, 1.0)
    source_score   = 1.0 if lead.source == "paid" else 0.5

    score = round(
        MAUT_WEIGHTS["company"]   * company_score
        + MAUT_WEIGHTS["industry"]  * industry_score
        + MAUT_WEIGHTS["employees"] * employee_score
        + MAUT_WEIGHTS["message"]   * message_score
        + MAUT_WEIGHTS["source"]    * source_score,
        4,
    )

    if score >= 0.75:
        tier  = "Hot"
        route = "Notion CRM + Slack immediate + Apollo sequence A"
        background_tasks.add_task(_fire_apollo_enroll, lead, tier)
    elif score >= 0.45:
        tier  = "Warm"
        route = "Notion CRM + Slack summary digest"
    else:
        tier  = "Cold"
        route = "Notion CRM only — no immediate action"

    return LeadScore(
        score=score,
        tier=tier,
        route=route,
        explanation={
            "company":   round(MAUT_WEIGHTS["company"]   * company_score,  4),
            "industry":  round(MAUT_WEIGHTS["industry"]  * industry_score, 4),
            "employees": round(MAUT_WEIGHTS["employees"] * employee_score, 4),
            "message":   round(MAUT_WEIGHTS["message"]   * message_score,  4),
            "source":    round(MAUT_WEIGHTS["source"]    * source_score,   4),
        },
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "garcar-lead-scorer"}
