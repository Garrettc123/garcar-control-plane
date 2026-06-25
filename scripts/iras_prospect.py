#!/usr/bin/env python3
"""
IRAS Prospecting Agent — DFW Roofing Contractors

Sources (in priority order):
  1. Google Places API — "roofing contractor" near Dallas/Fort Worth
  2. BuildZoom public API — licensed contractor search
  3. HomeAdvisor scrape — pro directory fallback

Outputs leads to Supabase iras_leads table.
Prints batch_id and leads_discovered to stdout for GHA output capture.

Usage:
  python scripts/iras_prospect.py --batch-id <uuid> --limit 50 --dry-run
"""

import os
import sys
import json
import uuid
import argparse
import time
import re
import httpx
from datetime import datetime, timezone
from supabase import create_client

# DFW metro area coordinates and radius
DFW_LOCATIONS = [
    {"name": "Dallas",       "lat": 32.7767,  "lng": -96.7970},
    {"name": "Fort Worth",   "lat": 32.7555,  "lng": -97.3308},
    {"name": "Plano",        "lat": 33.0198,  "lng": -96.6989},
    {"name": "Frisco",       "lat": 33.1507,  "lng": -96.8236},
    {"name": "Arlington",    "lat": 32.7357,  "lng": -97.1081},
    {"name": "McKinney",     "lat": 33.1972,  "lng": -96.6397},
    {"name": "Garland",      "lat": 32.9126,  "lng": -96.6389},
    {"name": "Irving",       "lat": 32.8140,  "lng": -96.9489},
    {"name": "Denton",       "lat": 33.2148,  "lng": -97.1331},
    {"name": "Mesquite",     "lat": 32.7668,  "lng": -96.5992},
]

RADIUS_METERS = 15000  # 15km per city
SPECIALTY = "roofing"


def scrape_google_places(api_key: str, limit: int) -> list[dict]:
    """Query Google Places Text Search for roofing contractors in DFW."""
    leads = []
    seen_place_ids = set()

    for location in DFW_LOCATIONS:
        if len(leads) >= limit:
            break

        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{location['lat']},{location['lng']}",
            "radius": RADIUS_METERS,
            "keyword": "roofing contractor",
            "type": "general_contractor",
            "key": api_key,
        }

        try:
            resp = httpx.get(url, params=params, timeout=15)
            data = resp.json()
        except Exception as e:
            print(f"[PROSPECT] Google Places error for {location['name']}: {e}", file=sys.stderr)
            continue

        for place in data.get("results", []):
            if len(leads) >= limit:
                break

            place_id = place.get("place_id")
            if not place_id or place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            name = place.get("name", "")
            vicinity = place.get("vicinity", "")
            rating = place.get("rating", 0)
            review_count = place.get("user_ratings_total", 0)

            # Skip chains and franchises
            if any(chain in name.lower() for chain in ["lowes", "home depot", "abc supply", "menards"]):
                continue

            # Fetch place details for phone + website
            detail = fetch_place_details(api_key, place_id)
            phone = detail.get("formatted_phone_number", "")
            website = detail.get("website", "")
            email = extract_email_from_website(website) if website else ""

            lead = {
                "company_name": name,
                "specialty": SPECIALTY,
                "phone": phone,
                "email": email or None,
                "linkedin_url": None,
                "pain_data": json.dumps({
                    "source": "google_places",
                    "city": location["name"],
                    "rating": rating,
                    "review_count": review_count,
                    "vicinity": vicinity,
                    "website": website,
                }),
            }
            leads.append(lead)
            time.sleep(0.1)  # rate limit

        # Handle pagination
        next_page_token = data.get("next_page_token")
        if next_page_token and len(leads) < limit:
            time.sleep(2)  # Google requires delay before next_page_token is valid
            resp2 = httpx.get(url, params={"pagetoken": next_page_token, "key": api_key}, timeout=15)
            for place in resp2.json().get("results", []):
                if len(leads) >= limit:
                    break
                place_id = place.get("place_id")
                if place_id and place_id not in seen_place_ids:
                    seen_place_ids.add(place_id)
                    detail = fetch_place_details(api_key, place_id)
                    leads.append({
                        "company_name": place.get("name", ""),
                        "specialty": SPECIALTY,
                        "phone": detail.get("formatted_phone_number", ""),
                        "email": extract_email_from_website(detail.get("website", "")) or None,
                        "linkedin_url": None,
                        "pain_data": json.dumps({"source": "google_places", "city": location["name"]}),
                    })

    return leads


def fetch_place_details(api_key: str, place_id: str) -> dict:
    """Fetch phone and website for a single place."""
    try:
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={"place_id": place_id, "fields": "formatted_phone_number,website", "key": api_key},
            timeout=10,
        )
        return resp.json().get("result", {})
    except Exception:
        return {}


def extract_email_from_website(url: str) -> str:
    """Best-effort email extraction from a contractor's homepage."""
    if not url:
        return ""
    try:
        resp = httpx.get(url, timeout=8, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        # Skip info@ and contact@ — IRAS only wants direct owner emails
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", resp.text)
        for email in emails:
            domain = email.split("@")[1].lower()
            local = email.split("@")[0].lower()
            if any(skip in local for skip in ["info", "contact", "hello", "admin", "support", "noreply", "no-reply"]):
                continue
            if any(skip in domain for skip in ["example", "sentry", "wix", "squarespace", "godaddy"]):
                continue
            return email
    except Exception:
        pass
    return ""


def buildzoom_search(limit: int) -> list[dict]:
    """
    BuildZoom public contractor search — no API key required.
    Scrapes the public search results for licensed roofing contractors in DFW.
    """
    leads = []
    cities = ["dallas-tx", "fort-worth-tx", "plano-tx", "frisco-tx", "mckinney-tx"]

    for city in cities:
        if len(leads) >= limit:
            break
        try:
            url = f"https://www.buildzoom.com/contractors/roofing-contractors/{city}"
            resp = httpx.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            # Extract contractor names and contact info from HTML
            names = re.findall(r'<h2[^>]*class="[^"]*contractor-name[^"]*"[^>]*>([^<]+)</h2>', resp.text)
            phones = re.findall(r'tel:([\d\-\(\) ]+)', resp.text)

            for i, name in enumerate(names):
                if len(leads) >= limit:
                    break
                leads.append({
                    "company_name": name.strip(),
                    "specialty": SPECIALTY,
                    "phone": phones[i].strip() if i < len(phones) else "",
                    "email": None,
                    "linkedin_url": None,
                    "pain_data": json.dumps({"source": "buildzoom", "city": city}),
                })
        except Exception as e:
            print(f"[PROSPECT] BuildZoom error for {city}: {e}", file=sys.stderr)

    return leads


def write_leads_to_supabase(supabase, batch_id: str, leads: list[dict]) -> int:
    """Upsert leads into iras_leads. Skip duplicates by email."""
    written = 0
    for lead in leads:
        if not lead.get("company_name"):
            continue
        try:
            record = {
                "id": str(uuid.uuid4()),
                "batch_id": batch_id,
                "status": "prospected",
                "company_name": lead["company_name"],
                "specialty": lead.get("specialty", SPECIALTY),
                "phone": lead.get("phone") or None,
                "email": lead.get("email") or None,
                "linkedin_url": lead.get("linkedin_url") or None,
                "pain_data": lead.get("pain_data"),
                "score": 20,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            # Upsert on email — skip if email already exists in pipeline
            if record["email"]:
                supabase.table("iras_leads").upsert(record, on_conflict="email", ignore_duplicates=True).execute()
            else:
                supabase.table("iras_leads").insert(record).execute()
            written += 1
        except Exception as e:
            print(f"[PROSPECT] Skipping {lead.get('company_name')}: {e}", file=sys.stderr)

    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default=str(uuid.uuid4()))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch_id = args.batch_id
    limit = args.limit
    dry_run = args.dry_run

    print(f"[PROSPECT] Starting | batch={batch_id} | limit={limit} | dry_run={dry_run}")

    google_api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")

    # Source 1: Google Places (primary)
    leads = []
    if google_api_key:
        print("[PROSPECT] Querying Google Places...")
        leads = scrape_google_places(google_api_key, limit)
        print(f"[PROSPECT] Google Places: {len(leads)} candidates")
    else:
        print("[PROSPECT] GOOGLE_PLACES_API_KEY not set — falling back to BuildZoom", file=sys.stderr)

    # Source 2: BuildZoom fallback
    if len(leads) < limit:
        print("[PROSPECT] Querying BuildZoom...")
        bz_leads = buildzoom_search(limit - len(leads))
        leads.extend(bz_leads)
        print(f"[PROSPECT] BuildZoom: {len(bz_leads)} additional")

    # Deduplicate by company name
    seen_names = set()
    unique_leads = []
    for lead in leads:
        name_key = lead["company_name"].lower().strip()
        if name_key not in seen_names:
            seen_names.add(name_key)
            unique_leads.append(lead)
    leads = unique_leads[:limit]

    print(f"[PROSPECT] {len(leads)} unique leads after dedup")

    if dry_run:
        print("[PROSPECT] Dry run — skipping Supabase write")
        for lead in leads[:5]:
            print(f"  Sample: {lead['company_name']} | {lead.get('phone','')} | {lead.get('email','')}")
    else:
        supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        written = write_leads_to_supabase(supabase, batch_id, leads)
        supabase.table("iras_batches").update({
            "leads_discovered": written,
            "status": "prospected"
        }).eq("id", batch_id).execute()
        print(f"[PROSPECT] {written} leads written to Supabase")

    # GHA output
    gha_output = os.environ.get("GITHUB_OUTPUT")
    if gha_output:
        with open(gha_output, "a") as f:
            f.write(f"leads_discovered={len(leads)}\n")
            f.write(f"batch_id={batch_id}\n")

    print(f"[PROSPECT] Done — batch_id={batch_id} leads={len(leads)}")


if __name__ == "__main__":
    main()
