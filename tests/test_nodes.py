"""
Unit tests for LangGraph node logic — pure state transforms, no LLM calls.
Tests node_process_text and node_detect_crisis.
"""

import pytest
from src.agents.nodes import (
    node_process_text,
    node_detect_crisis,
    _clean_text,
    _compute_engagement,
)


def _base_state(**overrides):
    """Minimal valid AnalysisState for testing."""
    state = {
        "job_id": "test-job-123",
        "brand_name": "TestBrand",
        "raw_posts": [],
        "processed_posts": [],
        "total_posts": 0,
        "platform_breakdown": {},
        "analyzed_posts": [],
        "sentiment_distribution": {"positive": 0.0, "negative": 0.0, "neutral": 0.0},
        "weighted_sentiment": {},
        "aspect_results": {},
        "insight_summary": "",
        "key_themes": [],
        "recommendations": [],
        "crisis_score": 0.0,
        "crisis_triggered": False,
        "crisis_details": {},
        "errors": [],
        "current_node": "",
    }
    state.update(overrides)
    return state


# ── node_process_text: deduplication ─────────────────────────────────────────


class TestNodeProcessText:
    def test_deduplication(self):
        posts = [
            {
                "id": "1",
                "platform": "reddit",
                "title": "Duplicate title here for testing",
                "text": "body text here",
                "platform_meta": {},
            },
            {
                "id": "2",
                "platform": "reddit",
                "title": "Duplicate title here for testing",
                "text": "body text here",
                "platform_meta": {},
            },
        ]
        state = _base_state(raw_posts=posts)
        result = node_process_text(state)
        assert result["total_posts"] == 1

    def test_short_text_dropped(self):
        posts = [
            {
                "id": "1",
                "platform": "reddit",
                "title": "",
                "text": "hi",
                "platform_meta": {},
            },
            {
                "id": "2",
                "platform": "reddit",
                "title": "This is a valid long enough title",
                "text": "with enough body",
                "platform_meta": {},
            },
        ]
        state = _base_state(raw_posts=posts)
        result = node_process_text(state)
        assert result["total_posts"] == 1

    def test_platform_breakdown_counted(self):
        posts = [
            {
                "id": "1",
                "platform": "reddit",
                "title": "Reddit post about something",
                "text": "body text here",
                "platform_meta": {},
            },
            {
                "id": "2",
                "platform": "youtube",
                "title": "YouTube post about something",
                "text": "body text here",
                "platform_meta": {},
            },
            {
                "id": "3",
                "platform": "hackernews",
                "title": "HN post about something new",
                "text": "body text here",
                "platform_meta": {},
            },
        ]
        state = _base_state(raw_posts=posts)
        result = node_process_text(state)
        assert result["platform_breakdown"]["reddit"] == 1
        assert result["platform_breakdown"]["youtube"] == 1
        assert result["platform_breakdown"]["hackernews"] == 1

    def test_engagement_score_added(self):
        posts = [
            {
                "id": "1",
                "platform": "reddit",
                "title": "A valid post title long enough",
                "text": "some text body",
                "platform_meta": {"score": 500, "num_comments": 100},
            },
        ]
        state = _base_state(raw_posts=posts)
        result = node_process_text(state)
        post = result["processed_posts"][0]
        assert "engagement_score" in post
        assert post["engagement_score"] > 0


# ── _clean_text ──────────────────────────────────────────────────────────────


class TestCleanText:
    def test_removes_urls(self):
        text = "Check out https://example.com/page for info"
        cleaned = _clean_text(text)
        assert "https://" not in cleaned
        assert "example.com" not in cleaned

    def test_removes_html_tags(self):
        text = "This is <b>bold</b> and <a href='#'>linked</a>"
        cleaned = _clean_text(text)
        assert "<b>" not in cleaned
        assert "<a" not in cleaned
        assert "bold" in cleaned

    def test_collapses_whitespace(self):
        text = "too    many     spaces"
        cleaned = _clean_text(text)
        assert "  " not in cleaned

    def test_empty_string(self):
        assert _clean_text("") == ""
        assert _clean_text(None) == ""


# ── _compute_engagement ──────────────────────────────────────────────────────


class TestComputeEngagement:
    def test_reddit_formula(self):
        meta = {"score": 1000, "num_comments": 50}
        eng = _compute_engagement("reddit", meta)
        # (1000 * 0.01) + (50 * 0.1) = 10 + 5 = 15 → capped at 10.0
        assert eng == 10.0

    def test_reddit_low_score(self):
        meta = {"score": 10, "num_comments": 2}
        eng = _compute_engagement("reddit", meta)
        # (10 * 0.01) + (2 * 0.1) = 0.1 + 0.2 = 0.3
        assert abs(eng - 0.3) < 0.01

    def test_youtube_video(self):
        meta = {"content_type": "video", "views": 1_000_000, "likes": 10_000}
        eng = _compute_engagement("youtube", meta)
        # (1M * 0.000001) + (10k * 0.0001) = 1.0 + 1.0 = 2.0
        assert abs(eng - 2.0) < 0.01

    def test_youtube_comment(self):
        meta = {"content_type": "comment", "likes": 50}
        eng = _compute_engagement("youtube", meta)
        # 50 * 0.01 = 0.5
        assert abs(eng - 0.5) < 0.01

    def test_hackernews_formula(self):
        meta = {"points": 100, "num_comments": 50}
        eng = _compute_engagement("hackernews", meta)
        # (100 * 0.05) + (50 * 0.05) = 5.0 + 2.5 = 7.5
        assert abs(eng - 7.5) < 0.01

    def test_unknown_platform_default(self):
        eng = _compute_engagement("mastodon", {})
        assert eng == 1.0

    def test_capped_at_10(self):
        meta = {"score": 99999, "num_comments": 99999}
        eng = _compute_engagement("reddit", meta)
        assert eng == 10.0


# ── node_detect_crisis ───────────────────────────────────────────────────────


class TestNodeDetectCrisis:
    def test_high_negative_triggers_crisis(self):
        """crisis_score >= 1.0 when negative >= 0.60 (CRISIS_THRESHOLD)."""
        state = _base_state(
            sentiment_distribution={"positive": 0.1, "negative": 0.65, "neutral": 0.25},
            aspect_results={},
        )
        result = node_detect_crisis(state)
        assert result["crisis_triggered"] is True
        assert result["crisis_score"] >= 1.0

    def test_concern_range(self):
        """0.40 <= negative < 0.60 → concern but NOT crisis."""
        state = _base_state(
            sentiment_distribution={"positive": 0.2, "negative": 0.50, "neutral": 0.3},
            aspect_results={},
        )
        result = node_detect_crisis(state)
        assert result["crisis_triggered"] is False
        assert result["crisis_score"] < 1.0
        assert result["crisis_details"]["is_concern"] is True

    def test_clean_state(self):
        """negative < 0.40 → no concern, no crisis."""
        state = _base_state(
            sentiment_distribution={"positive": 0.5, "negative": 0.2, "neutral": 0.3},
            aspect_results={},
        )
        result = node_detect_crisis(state)
        assert result["crisis_triggered"] is False
        assert result["crisis_details"]["is_concern"] is False

    def test_top_concern_from_aspects(self):
        state = _base_state(
            sentiment_distribution={"positive": 0.1, "negative": 0.7, "neutral": 0.2},
            aspect_results={
                "pricing": {
                    "count": 10,
                    "positive": 0.1,
                    "negative": 0.8,
                    "neutral": 0.1,
                    "avg_intensity": 0.7,
                },
                "product": {
                    "count": 5,
                    "positive": 0.6,
                    "negative": 0.2,
                    "neutral": 0.2,
                    "avg_intensity": 0.4,
                },
            },
        )
        result = node_detect_crisis(state)
        assert "pricing" in result["crisis_details"]["top_concern"]

    def test_exact_threshold_triggers(self):
        """Exactly 0.60 negative → crisis_score = 1.0 → crisis triggered."""
        state = _base_state(
            sentiment_distribution={"positive": 0.1, "negative": 0.60, "neutral": 0.3},
            aspect_results={},
        )
        result = node_detect_crisis(state)
        # Use approx tolerance instead of exact >= 1.0
        assert result["crisis_score"] == pytest.approx(1.0, abs=1e-6)
        assert result["crisis_triggered"] is True
