"""
Google Ads daily sync — fetches campaign spend/clicks/conversions for the last 7 days.
Upserts to Supabase ad_spend table and posts Slack ROAS summary.
Gracefully no-ops when credentials are absent (safe for CI runs).
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.error

GOOGLE_ADS_DEV_TOKEN  = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
GOOGLE_ADS_CUSTOMER_ID = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")
GOOGLE_OAUTH_TOKEN     = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN", "")
SUPABASE_URL           = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY   = os.environ.get("SUPABASE_SERVICE_KEY", "")
SLACK_WEBHOOK_URL      = os.environ.get("SLACK_WEBHOOK_URL", "")


def post_json(url: str, data, headers: dict = None, method: str = "POST"):
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[warn] {method} {url[:80]} -> {e.code}: {e.read().decode()[:400]}")
        return None


def get_google_ads_campaigns() -> list:
    if not GOOGLE_OAUTH_TOKEN or not GOOGLE_ADS_CUSTOMER_ID:
        print("[google-ads] credentials not set — skipping API call")
        return []

    customer_id = GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
    end_date    = datetime.date.today()
    start_date  = end_date - datetime.timedelta(days=7)

    query = (
        f"SELECT campaign.name, segments.date, metrics.cost_micros, "
        f"metrics.clicks, metrics.conversions, metrics.conversions_value "
        f"FROM campaign "
        f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}' "
        f"AND campaign.status = 'ENABLED' "
        f"ORDER BY segments.date DESC LIMIT 500"
    )

    req = urllib.request.Request(
        f"https://googleads.googleapis.com/v16/customers/{customer_id}/googleAds:search",
        data=json.dumps({"query": query}).encode(),
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {GOOGLE_OAUTH_TOKEN}")
    req.add_header("developer-token", GOOGLE_ADS_DEV_TOKEN)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[google-ads] API error {e.code}: {e.read().decode()[:300]}")
        return []

    rows = []
    for row in data.get("results", []):
        rows.append({
            "date":        row["segments"]["date"],
            "platform":    "google",
            "campaign":    row["campaign"]["name"],
            "spend":       round(int(row["metrics"].get("costMicros", 0)) / 1_000_000, 2),
            "clicks":      int(row["metrics"].get("clicks", 0)),
            "conversions": float(row["metrics"].get("conversions", 0)),
            "revenue":     float(row["metrics"].get("conversionsValue", 0)),
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
    roas = total_revenue / total_spend if total_spend > 0 else 0
    campaigns = len(set(r["campaign"] for r in rows))
    post_json(
        SLACK_WEBHOOK_URL,
        {"text": (
            f":bar_chart: *Google Ads Sync — Last 7 Days*\n"
            f"Spend: ${total_spend:,.2f} | Revenue: ${total_revenue:,.2f} | ROAS: {roas:.2f}x\n"
            f"Clicks: {total_clicks:,} | Campaigns: {campaigns} | Rows synced: {len(rows)}"
        )},
    )


def main():
    print("[google-ads-sync] starting...")
    rows = get_google_ads_campaigns()
    print(f"[google-ads-sync] fetched {len(rows)} rows")
    upsert_to_supabase(rows)
    post_slack_summary(rows)
    print("[google-ads-sync] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
