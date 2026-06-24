"""
Meta Ads daily sync — fetches Facebook/Instagram campaign insights for the last 7 days.
Upserts to Supabase ad_spend table and posts Slack ROAS summary.
Gracefully no-ops when credentials are absent.
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.error
import urllib.parse

META_ACCESS_TOKEN    = os.environ.get("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID   = os.environ.get("META_AD_ACCOUNT_ID", "")
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SLACK_WEBHOOK_URL    = os.environ.get("SLACK_WEBHOOK_URL", "")

META_GRAPH_URL = "https://graph.facebook.com/v19.0"


def get_json(url: str):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[warn] GET -> {e.code}: {e.read().decode()[:200]}")
        return None


def post_json(url: str, data, headers: dict = None):
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[warn] POST {url[:80]} -> {e.code}: {e.read().decode()[:200]}")
        return None


def get_meta_campaigns() -> list:
    if not META_ACCESS_TOKEN or not META_AD_ACCOUNT_ID:
        print("[meta-ads] credentials not set — skipping API call")
        return []

    end_date   = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=7)

    params = urllib.parse.urlencode({
        "access_token": META_ACCESS_TOKEN,
        "fields": "campaign_name,spend,clicks,actions,action_values",
        "time_range": json.dumps({"since": str(start_date), "until": str(end_date)}),
        "level": "campaign",
        "limit": 100,
    })
    url  = f"{META_GRAPH_URL}/act_{META_AD_ACCOUNT_ID}/insights?{params}"
    data = get_json(url)
    if not data:
        return []

    rows = []
    for entry in data.get("data", []):
        actions       = {a["action_type"]: float(a["value"]) for a in entry.get("actions", [])}
        action_values = {a["action_type"]: float(a["value"]) for a in entry.get("action_values", [])}
        conversions   = actions.get("purchase", 0) + actions.get("lead", 0)
        revenue       = action_values.get("purchase", 0)
        rows.append({
            "date":        str(end_date),
            "platform":    "meta",
            "campaign":    entry.get("campaign_name", "unknown"),
            "spend":       round(float(entry.get("spend", 0)), 2),
            "clicks":      int(entry.get("clicks", 0)),
            "conversions": conversions,
            "revenue":     revenue,
        })
    return rows


def upsert_to_supabase(rows: list):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not rows:
        print(f"[supabase] skip — {len(rows)} rows, url={'set' if SUPABASE_URL else 'missing'}")
        return
    post_json(
        f"{SUPABASE_URL}/rest/v1/ad_spend",
        rows,
        {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Prefer": "resolution=merge-duplicates",
        },
    )
    print(f"[supabase] upserted {len(rows)} rows")


def post_slack_summary(rows: list):
    if not SLACK_WEBHOOK_URL or not rows:
        return
    total_spend   = sum(r.get("spend", 0) for r in rows)
    total_revenue = sum(r.get("revenue", 0) for r in rows)
    total_clicks  = sum(r.get("clicks", 0) for r in rows)
    roas      = total_revenue / total_spend if total_spend > 0 else 0
    campaigns = len(set(r["campaign"] for r in rows))
    post_json(
        SLACK_WEBHOOK_URL,
        {"text": (
            f":bar_chart: *Meta Ads Sync — Last 7 Days*\n"
            f"Spend: ${total_spend:,.2f} | Revenue: ${total_revenue:,.2f} | ROAS: {roas:.2f}x\n"
            f"Clicks: {total_clicks:,} | Campaigns: {campaigns} | Rows synced: {len(rows)}"
        )},
    )


def main():
    print("[meta-ads-sync] starting...")
    rows = get_meta_campaigns()
    print(f"[meta-ads-sync] fetched {len(rows)} rows")
    upsert_to_supabase(rows)
    post_slack_summary(rows)
    print("[meta-ads-sync] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
