import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import main as svc


def test_get_campaigns_returns_empty_without_credentials():
    original_token = svc.META_ACCESS_TOKEN
    original_id = svc.META_AD_ACCOUNT_ID
    try:
        svc.META_ACCESS_TOKEN = ""
        svc.META_AD_ACCOUNT_ID = ""
        assert svc.get_meta_campaigns() == []
    finally:
        svc.META_ACCESS_TOKEN = original_token
        svc.META_AD_ACCOUNT_ID = original_id


def test_upsert_to_supabase_skips_without_url():
    with patch.object(svc, 'post_json') as mock_post:
        svc.upsert_to_supabase([{"date": "2026-06-24", "platform": "meta"}])
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
        rows = [{"date": "2026-06-24", "platform": "meta", "campaign": "test",
                 "spend": 150, "clicks": 80, "conversions": 3, "revenue": 450}]
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


def test_post_slack_summary_includes_roas_and_meta_label():
    original_webhook = svc.SLACK_WEBHOOK_URL
    try:
        svc.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"
        rows = [{"spend": 500, "revenue": 2500, "clicks": 200, "campaign": "meta-roofing"}]
        with patch.object(svc, 'post_json') as mock_post:
            svc.post_slack_summary(rows)
            mock_post.assert_called_once()
            text = mock_post.call_args[0][1]["text"]
            assert "Meta Ads" in text
            assert "ROAS" in text
            assert "5.00x" in text
    finally:
        svc.SLACK_WEBHOOK_URL = original_webhook


def test_main_exits_zero_without_credentials():
    assert svc.main() == 0
