import os
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from enroll import enroll_lead

app = FastAPI(title="Garcar Apollo Enroll", version="1.0.0")


class LeadEnrollRequest(BaseModel):
    name: Optional[str] = None
    email: str
    company: Optional[str] = None
    industry: Optional[str] = None
    tier: Optional[str] = "hot"
    utm_campaign: Optional[str] = None


@app.post("/enroll")
async def enroll(lead: LeadEnrollRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(enroll_lead, lead.model_dump())
    return {"status": "queued", "email": lead.email}


@app.get("/health")
def health():
    return {"status": "ok", "service": "apollo-enroll"}
