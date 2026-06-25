#!/usr/bin/env python3
import os, sys, json, uuid, argparse, time, re, httpx
from datetime import datetime, timezone
from supabase import create_client

DFW_LOCATIONS = [
    {"name": "Dallas",     "lat": 32.7767, "lng": -96.7970},
    {"name": "Fort Worth", "lat": 32.7555, "lng": -97.3308},
    {"name": "Plano",      "lat": 33.0198, "lng": -96.6989},
    {"name": "Frisco",     "lat": 33.1507, "lng": -96.8236},
    {"name": "Arlington",  "lat": 32.7357, "lng": -97.1081},
    {"name": "McKinney",   "lat": 33.1972, "lng": -96.6397},
    {"name": "Garland",    "lat": 32.9126, "lng": -96.6389},
    {"name": "Irving",     "lat": 32.8140, "lng": -96.9489},
    {"name": "Denton",     "lat": 33.2148, "lng": -97.1331},
    {"name": "Mesquite",   "lat": 32.7668, "lng": -96.5992},
]
RADIUS_METERS = 15000
SPECIALTY = "roofing"
SKIP_CHAINS = ["lowes", "home depot", "abc supply", "menards"]
SKIP_LOCAL = ["info", "contact", "hello", "admin", "support", "noreply", "no-reply"]
SKIP_DOMAIN = ["example", "sentry", "wix", "squarespace", "godaddy"]

def fetch_place_details(api_key, place_id):
    try:
        r = httpx.get("https://maps.googleapis.com/maps/api/place/details/json",
            params={"place_id": place_id, "fields": "formatted_phone_number,website", "key": api_key}, timeout=10)
        return r.json().get("result", {})
    except: return {}

def extract_email(url):
    if not url: return ""
    try:
        r = httpx.get(url, timeout=8, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        for email in re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", r.text):
            local, domain = email.split("@")[0].lower(), email.split("@")[1].lower()
            if any(s in local for s in SKIP_LOCAL): continue
            if any(s in domain for s in SKIP_DOMAIN): continue
            return email
    except: pass
    return ""

def scrape_google_places(api_key, limit):
    leads = []; seen = set()
    for loc in DFW_LOCATIONS:
        if len(leads) >= limit: break
        try:
            r = httpx.get("https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={"location": f"{loc['lat']},{loc['lng']}", "radius": RADIUS_METERS,
                        "keyword": "roofing contractor", "type": "general_contractor", "key": api_key}, timeout=15)
            data = r.json()
        except Exception as e: print(f"[PROSPECT] Places error {loc['name']}: {e}", file=sys.stderr); continue
        for p in data.get("results", []):
            if len(leads) >= limit: break
            pid = p.get("place_id")
            if not pid or pid in seen: continue
            seen.add(pid)
            name = p.get("name", "")
            if any(c in name.lower() for c in SKIP_CHAINS): continue
            detail = fetch_place_details(api_key, pid)
            website = detail.get("website", "")
            leads.append({"company_name": name, "specialty": SPECIALTY,
                "phone": detail.get("formatted_phone_number", ""),
                "email": extract_email(website) or None,
                "pain_data": json.dumps({"source": "google_places", "city": loc["name"],
                    "rating": p.get("rating", 0), "website": website})})
            time.sleep(0.1)
    return leads

def buildzoom_search(limit):
    leads = []
    for city in ["dallas-tx", "fort-worth-tx", "plano-tx", "frisco-tx", "mckinney-tx"]:
        if len(leads) >= limit: break
        try:
            r = httpx.get(f"https://www.buildzoom.com/contractors/roofing-contractors/{city}",
                timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            names = re.findall(r'<h2[^>]*class="[^"]*contractor-name[^"]*"[^>]*>([^<]+)</h2>', r.text)
            phones = re.findall(r'tel:([\d\-\(\) ]+)', r.text)
            for i, name in enumerate(names):
                if len(leads) >= limit: break
                leads.append({"company_name": name.strip(), "specialty": SPECIALTY,
                    "phone": phones[i].strip() if i < len(phones) else "",
                    "email": None, "pain_data": json.dumps({"source": "buildzoom", "city": city})})
        except Exception as e: print(f"[PROSPECT] BuildZoom {city}: {e}", file=sys.stderr)
    return leads

def write_leads(supabase, batch_id, leads):
    written = 0
    for lead in leads:
        if not lead.get("company_name"): continue
        try:
            record = {"id": str(uuid.uuid4()), "batch_id": batch_id, "status": "prospected",
                "company_name": lead["company_name"], "specialty": lead.get("specialty", SPECIALTY),
                "phone": lead.get("phone") or None, "email": lead.get("email") or None,
                "pain_data": lead.get("pain_data"), "score": 20,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()}
            if record["email"]:
                supabase.table("iras_leads").upsert(record, on_conflict="email", ignore_duplicates=True).execute()
            else:
                supabase.table("iras_leads").insert(record).execute()
            written += 1
        except Exception as e: print(f"[PROSPECT] Skip {lead.get('company_name')}: {e}", file=sys.stderr)
    return written

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default=str(uuid.uuid4()))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(f"[PROSPECT] batch={args.batch_id} limit={args.limit} dry_run={args.dry_run}")
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    leads = []
    if api_key:
        leads = scrape_google_places(api_key, args.limit)
        print(f"[PROSPECT] Google Places: {len(leads)}")
    else:
        print("[PROSPECT] No GOOGLE_PLACES_API_KEY — using BuildZoom", file=sys.stderr)
    if len(leads) < args.limit:
        bz = buildzoom_search(args.limit - len(leads))
        leads.extend(bz); print(f"[PROSPECT] BuildZoom: {len(bz)}")
    seen = set(); unique = []
    for l in leads:
        k = l["company_name"].lower().strip()
        if k not in seen: seen.add(k); unique.append(l)
    leads = unique[:args.limit]
    print(f"[PROSPECT] {len(leads)} unique leads")
    if args.dry_run:
        print("[PROSPECT] Dry run — skipping write")
        for l in leads[:5]: print(f"  {l['company_name']} | {l.get('phone','')} | {l.get('email','')}")
    else:
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        written = write_leads(sb, args.batch_id, leads)
        sb.table("iras_batches").update({"leads_discovered": written, "status": "prospected"}).eq("id", args.batch_id).execute()
        print(f"[PROSPECT] {written} leads written")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f: f.write(f"leads_discovered={len(leads)}\nbatch_id={args.batch_id}\n")
    print(f"[PROSPECT] Done — batch_id={args.batch_id}")

if __name__ == "__main__": main()
