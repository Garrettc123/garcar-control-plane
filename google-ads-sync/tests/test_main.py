import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import main as svc


def test_get_campaigns_returns_empty_without_credentials():
    original_token = svc.GOOGLE_OAUTH_TOKEN
    original_cid = svc.GOOGLE_ADS_CUSTOMER_ID
    try:
        svc.GOOGLE_OAUTH_TOKEN = ""
        svc.GOOGLE_ADS_CUSTOMER_ID = ""
        assert svc.get_google_ads_campaigns() == []
    finally:
        svc.GOOGLE_OAUTH_TOKEN = original_token
        svc.GOOGLE_ADS_CUSTOMER_ID = original_cid


def test_upsert_to_supabase_skips_without_url():
    with patch.object(svc, 'post_json') as mock_post:
        svc.upsert_to_supabase([{"date": "2026-06-24", "platform": "google"}])
        mock_post.assert_not_called()


def test_upsert_to_supabase_skips_with_empty_rows():
    original_url = svc.SUPABASE_URL
    original_key = svc.SUPABASE_SERVICE_KEY
    try:
        svc.SUPABASE_URL = "https://example.supabase.co"
        svc.SUPABASE_SERVICE_KEY = "test-key"
        with patch.object(svc, 'post_json') as mock_post:
            svc.upsert_to_supabase([])
            mock_post.assert_not_called()
    finally:
        svc.SUPABASE_URL = original_url
        svc.SUPABASE_SERVICE_KEY = original_key


def test_upsert_to_supabase_posts_rows():
    original_url = svc.SUPABASE_URL
    original_key = svc.SUPABASE_SERVICE_KEY
    try:
        svc.SUPABASE_URL = "https://example.supabase.co"
        svc.SUPABASE_SERVICE_KEY = "test-key"
        rows = [{"date": "2026-06-24", "platform": "google", "campaign": "test",
                 "spend": 100, "clicks": 50, "conversions": 2, "revenue": 300}]
        with patch.object(svc, 'post_json') as mock_post:
            svc.upsert_to_supabase(rows)
            mock_post.assert_called_once()
            assert mock_post.call_args[0][1] == rows
    finally:
        svc.SUPABASE_URL = original_url
        svc.SUPABASE_SERVICE_KEY = original_key


def test_post_slack_summary_skips_without_webhook():
    rows = [{"spend": 100, "revenue": 300, "clicks": 50, "campaign": "test"}]
    with patch.object(svc, 'post_json') as mock_post:
        svc.post_slack_summary(rows)
        mock_post.assert_not_called()


def test_post_slack_summary_includes_roas_and_google_label():
    original_webhook = svc.SLACK_WEBHOOK_URL
    try:
        svc.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"
        rows = [
            {"spend": 200, "revenue": 800, "clicks": 100, "campaign": "roofing"},
            {"spend": 100, "revenue": 200, "clicks": 60, "campaign": "hvac"},
        ]
        with patch.object(svc, 'post_json') as mock_post:
            svc.post_slack_summary(rows)
            mock_post.assert_called_once()
            text = mock_post.call_args[0][1]["text"]
            assert "Google Ads" in text
            assert "ROAS" in text
            assert "Campaigns: 2" in text
    finally:
        svc.SLACK_WEBHOOK_URL = original_webhook


def test_main_exits_zero_without_credentials():
    assert svc.main() == 0
