"""
Unit tests for collectors — no network calls.
Tests query building, post standardization, fallback logic.
"""

import pytest
from src.data.collectors.base_collector import BaseCollector
from src.data.collectors.reddit_collector import RedditCollector
from src.data.collectors.hackernews_collector import HackerNewsCollector
from src.data.collectors.youtube_collector import YouTubeCollector


# ── BaseCollector._build_query ───────────────────────────────────────────────

class TestBuildQuery:
    @pytest.fixture
    def collector(self):
        """HackerNews doesn't need API keys, easiest to instantiate."""
        return HackerNewsCollector()

    def test_brand_name_quoted(self, collector):
        q = collector._build_query("Nike")
        assert '"Nike"' in q

    def test_emotional_indicators_included(self, collector):
        q = collector._build_query("Nike", include_emotional=True)
        # Should contain at least some emotional words
        assert "love" in q or "hate" in q or "best" in q

    def test_emotional_excluded_when_false(self, collector):
        q = collector._build_query("Nike", include_emotional=False)
        # Emotional words block should not appear
        assert "love" not in q

    def test_keywords_injected(self, collector):
        q = collector._build_query("Nike", keywords="shoes, running")
        assert "shoes" in q
        assert "running" in q

    def test_keywords_joined_with_or(self, collector):
        q = collector._build_query("Nike", keywords="shoes, running")
        assert "OR" in q

    def test_empty_keywords_ignored(self, collector):
        q1 = collector._build_query("Nike", keywords="")
        q2 = collector._build_query("Nike", keywords="   ")
        # Both should just have brand + emotional, no empty parens
        assert "()" not in q1
        assert "()" not in q2


# ── BaseCollector._make_post ─────────────────────────────────────────────────

class TestMakePost:
    @pytest.fixture
    def collector(self):
        return HackerNewsCollector()

    def test_post_has_required_fields(self, collector):
        post = collector._make_post(
            brand_name="Tesla",
            post_id="abc",
            title="Big news",
            text="Tesla is great",
        )
        assert "id" in post
        assert "platform" in post
        assert "title" in post
        assert "text" in post
        assert post["id"] == "abc"
        assert post["platform"] == "hackernews"

    def test_text_cleaning(self, collector):
        post = collector._make_post(
            brand_name="Tesla",
            post_id="1",
            title="  too   many   spaces  ",
            text="also\n\nmany   gaps",
        )
        assert "  " not in post["title"]
        assert "  " not in post["text"]

    def test_empty_text_handled(self, collector):
        post = collector._make_post(
            brand_name="Tesla",
            post_id="1",
            title="",
            text=None,
        )
        assert post["title"] == ""
        assert post["text"] == ""

    def test_platform_meta_preserved(self, collector):
        meta = {"score": 100, "num_comments": 50}
        post = collector._make_post(
            brand_name="Tesla",
            post_id="1",
            title="test",
            text="test",
            platform_meta=meta,
        )
        assert post["platform_meta"] == meta


# ── BaseCollector._clean_text ────────────────────────────────────────────────

class TestCleanText:
    @pytest.fixture
    def collector(self):
        return HackerNewsCollector()

    def test_collapses_whitespace(self, collector):
        assert collector._clean_text("hello    world") == "hello world"

    def test_handles_empty_string(self, collector):
        assert collector._clean_text("") == ""

    def test_handles_none(self, collector):
        # _clean_text checks `if not text` so empty-ish values return ""
        assert collector._clean_text(None) == ""


# ── 3-tier fallback strategy ─────────────────────────────────────────────────

class TestRedditStrategies:
    def test_three_strategies_generated(self):
        """RedditCollector.collect builds 3 query strategies."""
        collector = RedditCollector()
        brand = "Apple"
        strategies = [
            collector._build_query(brand, "", include_emotional=True),
            collector._build_query(brand, "", include_emotional=False),
            f'"{brand}"',
        ]
        assert len(strategies) == 3
        # 1st has emotional words, 2nd doesn't, 3rd is bare brand
        assert "love" in strategies[0] or "hate" in strategies[0]
        assert "love" not in strategies[1]
        assert strategies[2] == '"Apple"'


class TestYouTubeStrategies:
    def test_three_strategies_generated(self):
        collector = YouTubeCollector()
        brand = "Google"
        strategies = [
            collector._build_query(brand, "", include_emotional=True),
            collector._build_query(brand, "", include_emotional=False),
            brand,
        ]
        assert len(strategies) == 3
        assert strategies[2] == "Google"
