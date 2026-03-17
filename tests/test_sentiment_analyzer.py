"""
Unit tests for SentimentAnalyzer — pure logic, no LLM calls.
Tests scoring math, fallback output, build_output, filtering, distribution.
"""

import pytest
from src.analysis.sentiment_analyzer import SentimentAnalyzer


@pytest.fixture
def analyzer():
    """Analyzer with dummy keys — we never actually call LLMs here."""
    return SentimentAnalyzer(groq_api_key="fake-key")


# ── _empty_result ────────────────────────────────────────────────────────────

class TestEmptyResult:
    def test_empty_posts_returns_empty_result(self, analyzer):
        result = analyzer._empty_result()
        assert result["distribution"] == {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
        assert result["posts"] == []
        assert result["aspect_breakdown"] == {}

    async def test_analyze_empty_list(self, analyzer):
        result = await analyzer.analyze([], brand_name="Nike")
        assert result["posts"] == []
        assert result["distribution"]["positive"] == 0.0


# ── _neutral_fallback ────────────────────────────────────────────────────────

class TestNeutralFallback:
    def test_output_shape(self, analyzer):
        posts = [
            {"id": "p1", "text": "some text"},
            {"id": "p2", "text": "other text"},
        ]
        result = analyzer._neutral_fallback(posts)
        assert len(result) == 2
        for r in result:
            assert r["sentiment"] == "neutral"
            assert r["confidence"] == 0.5
            assert r["is_sarcastic"] is False
            assert r["aspect"] == "general"
            assert r["intensity"] == "mild"
            assert r["brand_relevance"] == 0.5

    def test_preserves_post_ids(self, analyzer):
        posts = [{"id": "abc123"}]
        result = analyzer._neutral_fallback(posts)
        assert result[0]["post_id"] == "abc123"


# ── _build_output ────────────────────────────────────────────────────────────

class TestBuildOutput:
    def test_distribution_sums_to_1(self, analyzer):
        llm_results = [
            {"post_id": "1", "sentiment": "positive", "confidence": 0.9,
             "brand_relevance": 0.8, "aspect": "product", "is_sarcastic": False},
            {"post_id": "2", "sentiment": "negative", "confidence": 0.7,
             "brand_relevance": 0.6, "aspect": "pricing", "is_sarcastic": False},
            {"post_id": "3", "sentiment": "neutral", "confidence": 0.5,
             "brand_relevance": 0.5, "aspect": "general", "is_sarcastic": False},
        ]
        original = [
            {"id": "1", "text": "great product"},
            {"id": "2", "text": "too expensive"},
            {"id": "3", "text": "it exists"},
        ]
        result = analyzer._build_output(llm_results, original, "TestBrand")
        dist = result["distribution"]
        total = dist["positive"] + dist["negative"] + dist["neutral"]
        assert abs(total - 1.0) < 0.01

    def test_brand_relevance_filter(self, analyzer):
        """Posts with brand_relevance < 0.3 should be excluded from distribution."""
        llm_results = [
            {"post_id": "1", "sentiment": "positive", "confidence": 0.9,
             "brand_relevance": 0.8, "aspect": "product"},
            {"post_id": "2", "sentiment": "negative", "confidence": 0.7,
             "brand_relevance": 0.1, "aspect": "general"},  # below threshold
        ]
        original = [
            {"id": "1", "text": "love it"},
            {"id": "2", "text": "off topic"},
        ]
        result = analyzer._build_output(llm_results, original, "TestBrand")
        # Only 1 relevant post → distribution based on 1 post
        assert result["relevant_count"] == 1
        assert result["distribution"]["positive"] == 1.0

    def test_mixed_sentiments(self, analyzer):
        llm_results = [
            {"post_id": str(i), "sentiment": s, "confidence": 0.8,
             "brand_relevance": 0.9, "aspect": "general"}
            for i, s in enumerate(["positive", "positive", "negative", "neutral"])
        ]
        original = [{"id": str(i), "text": f"text {i}"} for i in range(4)]
        result = analyzer._build_output(llm_results, original, "TestBrand")
        assert result["distribution"]["positive"] == 0.5
        assert result["distribution"]["negative"] == 0.25
        assert result["distribution"]["neutral"] == 0.25

    def test_enriched_posts_have_scores(self, analyzer):
        llm_results = [
            {"post_id": "1", "sentiment": "positive", "confidence": 0.85,
             "brand_relevance": 0.9, "aspect": "product", "is_sarcastic": False,
             "intensity": "strong", "reason": "users love it"},
        ]
        original = [{"id": "1", "text": "amazing product"}]
        result = analyzer._build_output(llm_results, original, "TestBrand")
        post = result["posts"][0]
        assert "positive_score" in post
        assert "negative_score" in post
        assert "neutral_score" in post
        assert "emotional_intensity" in post
        assert post["sentiment"] == "positive"
        assert post["sentiment_source"] == "llm"

    def test_aspect_breakdown(self, analyzer):
        llm_results = [
            {"post_id": "1", "sentiment": "positive", "confidence": 0.8,
             "brand_relevance": 0.9, "aspect": "product"},
            {"post_id": "2", "sentiment": "negative", "confidence": 0.8,
             "brand_relevance": 0.9, "aspect": "product"},
            {"post_id": "3", "sentiment": "positive", "confidence": 0.8,
             "brand_relevance": 0.9, "aspect": "pricing"},
        ]
        original = [{"id": str(i), "text": f"t{i}"} for i in range(1, 4)]
        result = analyzer._build_output(llm_results, original, "TestBrand")
        aspects = result["aspect_breakdown"]
        assert "product" in aspects
        assert aspects["product"]["positive"] == 1
        assert aspects["product"]["negative"] == 1
        assert "pricing" in aspects


# ── Engagement score math (via nodes, but tested through _build_output) ──────

class TestBatchFormatting:
    def test_fmt_truncates_long_text(self, analyzer):
        import json
        posts = [{"id": "1", "combined_text": "x" * 1000}]
        formatted = json.loads(analyzer._fmt(posts))
        assert len(formatted[0]["text"]) <= analyzer.MAX_CHARS
