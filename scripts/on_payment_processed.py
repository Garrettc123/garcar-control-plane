"""
on_payment_processed.py

Runs in GitHub Actions (garcar-control-plane) whenever garcar-payment-loop
dispatches payment_processed. Logs the event to control_plane_events in
Supabase and pings garcar-rhns-core so /cognitive/brief updates immediately.
"""
import logging
import os

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("control-plane")

TRACE_ID = os.environ.get("TRACE_ID", "")
STRIPE_EVENT_ID = os.environ.get("STRIPE_EVENT_ID", "")
STRIPE_EVENT_TYPE = os.environ.get("STRIPE_EVENT_TYPE", "")
CUSTOMER_EMAIL = os.environ.get("CUSTOMER_EMAIL", "")
AMOUNT_TOTAL_RAW = os.environ.get("AMOUNT_TOTAL", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RHNS_API_URL = os.environ.get("RHNS_API_URL", "")

try:
    AMOUNT_TOTAL = int(AMOUNT_TOTAL_RAW) if AMOUNT_TOTAL_RAW and AMOUNT_TOTAL_RAW not in ("None", "") else None
except (ValueError, TypeError):
    AMOUNT_TOTAL = None


def log_to_supabase() -> bool:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        log.warning("supabase not configured — skipping event log")
        return False

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/control_plane_events"
    body = [{
        "trace_id": TRACE_ID,
        "stripe_event_id": STRIPE_EVENT_ID,
        "stripe_event_type": STRIPE_EVENT_TYPE,
        "customer_email": CUSTOMER_EMAIL or None,
        "amount_total": AMOUNT_TOTAL,
        "source": "garcar-payment-loop",
        "stage": "payment_processed",
    }]
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        r = httpx.post(url, json=body, headers=headers, timeout=5.0)
        if r.status_code in (200, 201):
            log.info("logged to control_plane_events trace=%s", TRACE_ID)
            return True
        log.error("supabase_error status=%d body=%s", r.status_code, r.text[:200])
        return False
    except Exception as e:
        log.error("supabase_failed err=%s", e)
        return False


def ping_rhns() -> None:
    if not RHNS_API_URL:
        log.info("RHNS_API_URL not set — skipping brief refresh")
        return
    try:
        r = httpx.get(f"{RHNS_API_URL}/cognitive/brief", timeout=5.0)
        if r.status_code == 200:
            brief = r.json()
            log.info(
                "rhns_brief mrr=%.2f customers=%d source=%s",
                brief.get("mrr_usd", 0),
                brief.get("active_subscriptions", 0),
                brief.get("data_source", "unknown"),
            )
        else:
            log.warning("rhns_ping status=%d", r.status_code)
    except Exception as e:
        log.warning("rhns_ping_failed err=%s", e)


def main() -> None:
    log.info(
        "payment_processed trace=%s type=%s amount_cents=%s email=%s",
        TRACE_ID, STRIPE_EVENT_TYPE, AMOUNT_TOTAL, CUSTOMER_EMAIL or "unknown",
    )
    log_to_supabase()
    ping_rhns()
    log.info("done")


if __name__ == "__main__":
    main()
