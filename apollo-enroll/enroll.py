import json
import os
import urllib.error
import urllib.request
from typing import Optional

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
APOLLO_EMAIL_ACCOUNT_ID = os.environ.get("APOLLO_EMAIL_ACCOUNT_ID", "")
APOLLO_SEQ_CONTRACTORS = os.environ.get("APOLLO_SEQ_CONTRACTORS", "")
APOLLO_SEQ_AGENCY = os.environ.get("APOLLO_SEQ_AGENCY", "")
APOLLO_SEQ_PTHCH = os.environ.get("APOLLO_SEQ_PTHCH", "")

_CONTRACTOR_KEYWORDS = {"contractor", "roofing", "construction", "hvac", "plumbing", "electrical", "landscaping"}
_AGENCY_KEYWORDS = {"agency", "marketing", "advertising", "digital"}


def _post(url: str, data: dict) -> Optional[dict]:
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Api-Key", APOLLO_API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        print(f"[apollo] {url.split('/')[-1]} HTTP {exc.code}: {exc.read().decode()[:200]}")
        return None
    except Exception as exc:
        print(f"[apollo] request error: {exc}")
        return None


def _pick_sequence(lead: dict) -> str:
    industry = (lead.get("industry") or "").lower()
    utm = (lead.get("utm_campaign") or "").lower()
    if "pthch" in utm or "audit" in utm:
        return APOLLO_SEQ_PTHCH
    if any(k in industry for k in _AGENCY_KEYWORDS):
        return APOLLO_SEQ_AGENCY
    return APOLLO_SEQ_CONTRACTORS


def enroll_lead(lead: dict) -> bool:
    """Upsert contact in Apollo and add to the correct sequence. Returns True on success."""
    if not APOLLO_API_KEY:
        print("[apollo] APOLLO_API_KEY not set — skipping enrollment")
        return False

    name_parts = (lead.get("name") or "").split(maxsplit=1)
    first = name_parts[0] if name_parts else ""
    last = name_parts[1] if len(name_parts) > 1 else ""

    contact_resp = _post(
        "https://api.apollo.io/v1/contacts",
        {
            "first_name": first,
            "last_name": last,
            "email": lead.get("email", ""),
            "organization_name": lead.get("company", ""),
            "label_names": ["garcar-inbound", (lead.get("tier") or "hot").lower()],
        },
    )
    if not contact_resp:
        return False

    contact_id = (contact_resp.get("contact") or {}).get("id")
    if not contact_id:
        print(f"[apollo] no contact id returned for {lead.get('email')}")
        return False

    sequence_id = _pick_sequence(lead)
    if not sequence_id:
        print("[apollo] no sequence ID configured — contact created, not enrolled")
        return True

    enroll_resp = _post(
        f"https://api.apollo.io/v1/emailer_campaigns/{sequence_id}/add_contact_ids",
        {
            "contact_ids": [contact_id],
            "send_email_from_email_account_id": APOLLO_EMAIL_ACCOUNT_ID,
        },
    )
    if not enroll_resp:
        return False

    print(f"[apollo] enrolled {lead.get('email')} → sequence {sequence_id}")
    return True
