#!/usr/bin/env python3
"""Sync Notion CRM → Supabase iras_leads + garcar_customers."""

import os
import json
import sys
import uuid
import requests
from datetime import datetime, timezone

_REQUIRED = ["NOTION_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
print("=== Secret check ===", flush=True)
_missing = []
for _s in _REQUIRED:
    _val = os.environ.get(_s, "")
    print(f"  {'SET   ' if _val else 'MISSING'}: {_s}", flush=True)
    if not _val:
        _missing.append(_s)
if _missing:
    print(f"\nERROR: {len(_missing)} required secret(s) not set in garcar-control-plane repository secrets.", flush=True)
    print("Go to: https://github.com/Garrettc123/garcar-control-plane/settings/secrets/actions", flush=True)
    print("Add under 'Repository secrets' (NOT under any environment):", flush=True)
    for _s in _missing:
        print(f"  {_s}", flush=True)
    sys.exit(1)
print("=== All secrets present ===", flush=True)

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_CRM_DB_ID = os.environ.get("NOTION_CRM_DB_ID", "8583f88b-69c8-4b55-9c1e-c32783d68ac1")
NOTION_CUSTOMERS_DB_ID = os.environ.get("NOTION_CUSTOMERS_DB_ID", "ee4024e8-799b-8335-89ed-8792ac238b5b")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

STAGE_TO_STATUS = {
    "New Lead": "prospected",
    "Contacted": "outreached",
    "Audit Scheduled": "scored",
    "Audit Delivered": "outreached",
    "Proposal Sent": "scored",
    "Negotiating": "scored",
    "Won": "customer",
    "Lost": "suppressed",
}

HEAT_TO_SCORE = {
    "Hot": 80,
    "Warm": 50,
    "Cold": 20,
}


def notion_query_db(db_id):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    results = []
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = requests.post(url, headers=NOTION_HEADERS, json=body)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return results


def prop(page, name):
    p = page["properties"].get(name, {})
    if not p:
        return None
    t = p.get("type")
    if t == "title":
        parts = p.get("title", [])
        return parts[0]["plain_text"] if parts else None
    if t == "rich_text":
        parts = p.get("rich_text", [])
        return parts[0]["plain_text"] if parts else None
    if t == "email":
        return p.get("email")
    if t == "phone_number":
        return p.get("phone_number")
    if t == "number":
        return p.get("number")
    if t == "select":
        s = p.get("select")
        return s["name"] if s else None
    if t == "multi_select":
        return [o["name"] for o in p.get("multi_select", [])]
    if t == "date":
        d = p.get("date")
        return d["start"] if d else None
    if t == "url":
        return p.get("url")
    if t == "checkbox":
        return p.get("checkbox", False)
    if t == "status":
        s = p.get("status")
        return s["name"] if s else None
    return None


def split_name(full_name):
    if not full_name:
        return None, None
    parts = full_name.strip().split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else None


def sync_crm_leads(batch_id):
    print("Fetching Notion CRM leads...")
    pages = notion_query_db(NOTION_CRM_DB_ID)
    print(f"  Found {len(pages)} records in Notion CRM")

    leads = []
    skipped = 0
    for page in pages:
        company = prop(page, "Company Name")
        contact = prop(page, "Contact Name")
        email = prop(page, "Email")
        phone = prop(page, "Phone")
        stage = prop(page, "Stage")
        heat = prop(page, "Heat")
        trade = prop(page, "Trade")
        notes = prop(page, "Notes")
        outreach_prompt = prop(page, "Outreach Prompt")
        last_contacted = prop(page, "Last Contacted")

        if not email:
            print(f"  Skipping {company or 'unknown'} — no email")
            skipped += 1
            continue

        first_name, last_name = split_name(contact)
        status = STAGE_TO_STATUS.get(stage, "prospected")
        score = HEAT_TO_SCORE.get(heat, 20)

        pain_data = {}
        if notes:
            pain_data["notes"] = notes
        if outreach_prompt:
            pain_data["outreach_prompt"] = outreach_prompt
        if trade:
            pain_data["trade"] = trade

        leads.append({
            "batch_id": batch_id,
            "email": email,
            "company_name": company,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "specialty": trade,
            "status": status,
            "score": score,
            "pain_data": pain_data,
            "enriched_at": last_contacted,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    print(f"  Syncing {len(leads)} leads ({skipped} skipped — no email)")

    if DRY_RUN:
        print(json.dumps(leads, indent=2, default=str))
        return len(leads)

    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/iras_leads",
        headers={**SUPABASE_HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
        json=leads,
    )
    if resp.status_code not in (200, 201):
        print(f"  ERROR {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    print(f"  Upserted {len(leads)} leads into iras_leads")
    return len(leads)


def sync_customers():
    print("Fetching Notion Customers DB...")
    pages = notion_query_db(NOTION_CUSTOMERS_DB_ID)
    print(f"  Found {len(pages)} records in Customers DB")

    customers = []
    skipped = 0
    for page in pages:
        name = prop(page, "Customer Name")
        email = prop(page, "Email")
        stripe_id = prop(page, "Stripe Customer ID")
        plan_list = prop(page, "Plan")
        customer_status = prop(page, "Customer Status")

        if not email and not stripe_id:
            skipped += 1
            continue

        plan = plan_list[0] if isinstance(plan_list, list) and plan_list else None
        status = "active" if customer_status == "Done" else "pending"
        first_name, _ = split_name(name)

        customers.append({
            "stripe_customer_id": stripe_id,
            "email": email,
            "first_name": first_name,
            "company": name,
            "plan": plan,
            "status": status,
            "onboarded_at": datetime.now(timezone.utc).isoformat(),
        })

    print(f"  Syncing {len(customers)} customers ({skipped} skipped)")

    if DRY_RUN:
        print(json.dumps(customers, indent=2, default=str))
        return len(customers)

    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/garcar_customers",
        headers={**SUPABASE_HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
        json=customers,
    )
    if resp.status_code not in (200, 201):
        print(f"  ERROR {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    print(f"  Upserted {len(customers)} customers into garcar_customers")
    return len(customers)


def main():
    batch_id = str(uuid.uuid4())
    print(f"Notion CRM sync | batch={batch_id} | dry_run={DRY_RUN}")

    if not DRY_RUN:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/iras_batches",
            headers={**SUPABASE_HEADERS, "Prefer": "return=representation"},
            json={
                "id": batch_id,
                "status": "notion_sync",
                "target_market": "notion_crm",
            },
        )
        if resp.status_code not in (200, 201):
            print(f"Batch create warning: {resp.status_code} {resp.text}")

    leads_count = sync_crm_leads(batch_id)
    customers_count = sync_customers()

    if not DRY_RUN:
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/iras_batches?id=eq.{batch_id}",
            headers=SUPABASE_HEADERS,
            json={
                "status": "notion_sync_complete",
                "leads_discovered": leads_count,
                "customers": customers_count,
            },
        )

    print(f"\nDone: {leads_count} leads, {customers_count} customers synced from Notion")
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"leads_synced={leads_count}\n")
        f.write(f"customers_synced={customers_count}\n")


if __name__ == "__main__":
    main()
