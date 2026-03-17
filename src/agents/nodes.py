# src/agents/nodes.py
import re
from collections import Counter
from typing import Any

from openai import AsyncOpenAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from src.agents.state import AnalysisState
from src.analysis.sentiment_analyzer import SentimentAnalyzer
from src.analysis.cache import get_cached, set_cached
from src.utils.config import settings
from src.utils.logger import get_logger


logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — Text Processing
# ══════════════════════════════════════════════════════════════════════════════


def node_process_text(state: AnalysisState) -> AnalysisState:
    logger.info(
        "node_process_text_start",
        job_id=state["job_id"],
        raw_count=len(state["raw_posts"]),
    )

    seen_texts: set[str] = set()
    processed = []
    platform_counts: dict[str, int] = {}

    for post in state["raw_posts"]:
        text = _clean_text(post.get("text", "") or "")
        title = _clean_text(post.get("title", "") or "")
        combined = f"{title} {text}".strip()

        if not combined or len(combined) < 10:
            continue

        fingerprint = combined[:100].lower()
        if fingerprint in seen_texts:
            continue
        seen_texts.add(fingerprint)

        platform = post.get("platform", "unknown")
        meta = post.get("platform_meta", {}) or {}
        engagement = _compute_engagement(platform, meta)

        processed.append(
            {
                **post,
                "text": text,
                "title": title,
                "combined_text": combined,
                "engagement_score": engagement,
            }
        )
        platform_counts[platform] = platform_counts.get(platform, 0) + 1

    logger.info(
        "node_process_text_done",
        job_id=state["job_id"],
        processed=len(processed),
        duplicates_removed=len(state["raw_posts"]) - len(processed),
    )

    return {
        **state,
        "processed_posts": processed,
        "total_posts": len(processed),
        "platform_breakdown": platform_counts,
        "current_node": "process_text",
    }


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\s.,!?\'-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _compute_engagement(platform: str, meta: dict) -> float:
    if platform == "reddit":
        score = meta.get("score", 0) or 0
        comments = meta.get("num_comments", 0) or 0
        return min(10.0, (score * 0.01) + (comments * 0.1))
    elif platform == "youtube":
        if meta.get("content_type", "video") == "video":
            views = meta.get("views", 0) or 0
            likes = meta.get("likes", 0) or 0
            return min(10.0, (views * 0.000001) + (likes * 0.0001))
        return min(10.0, (meta.get("likes", 0) or 0) * 0.01)
    elif platform == "hackernews":
        points = meta.get("points", 0) or 0
        comments = meta.get("num_comments", 0) or 0
        return min(10.0, (points * 0.05) + (comments * 0.05))
    return 1.0


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — Sentiment Analysis
# ══════════════════════════════════════════════════════════════════════════════


async def node_analyze_sentiment(state: AnalysisState) -> AnalysisState:
    posts = state["processed_posts"]
    brand_name = state["brand_name"]

    logger.info(
        "node_analyze_sentiment_start", job_id=state["job_id"], count=len(posts)
    )

    # ── Same-day cache check ──────────────────────────────────────────────
    cached = get_cached(brand_name)
    if cached:
        logger.info("sentiment_cache_hit", job_id=state["job_id"], brand=brand_name)
        return {
            **state,
            "analyzed_posts": cached["posts"],
            "sentiment_distribution": cached["distribution"],
            "weighted_sentiment": _compute_weighted_sentiment(cached["posts"]),
            "aspect_results": _build_aspect_results(cached["aspect_breakdown"]),
            "current_node": "analyze_sentiment",
        }

    # ── Normal path ───────────────────────────────────────────────────────
    analyzer = SentimentAnalyzer(
        groq_api_key=settings.groq_api_key,
        cerebras_api_key=getattr(settings, "cerebras_api_key", None),
    )
    result = await analyzer.analyze(posts, brand_name=brand_name)

    # ── Store in cache ────────────────────────────────────────────────────
    set_cached(brand_name, result)

    analyzed = result["posts"]
    dist = result["distribution"]
    weighted = _compute_weighted_sentiment(analyzed)
    aspect_results = _build_aspect_results(result["aspect_breakdown"])

    logger.info(
        "node_analyze_sentiment_done", job_id=state["job_id"], distribution=dist
    )

    return {
        **state,
        "analyzed_posts": analyzed,
        "sentiment_distribution": dist,
        "weighted_sentiment": weighted,
        "aspect_results": aspect_results,
        "current_node": "analyze_sentiment",
    }


def _compute_weighted_sentiment(posts: list[dict]) -> dict[str, float]:
    total_weight = sum(p.get("engagement_score", 1.0) for p in posts)
    if total_weight == 0:
        return {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    w_pos = sum(p["positive_score"] * p.get("engagement_score", 1.0) for p in posts)
    w_neg = sum(p["negative_score"] * p.get("engagement_score", 1.0) for p in posts)
    w_neu = sum(p["neutral_score"] * p.get("engagement_score", 1.0) for p in posts)
    return {
        "positive": round(w_pos / total_weight, 4),
        "negative": round(w_neg / total_weight, 4),
        "neutral": round(w_neu / total_weight, 4),
    }


def _build_aspect_results(aspect_breakdown: dict[str, dict]) -> dict[str, Any]:
    results = {}
    for aspect, counts in aspect_breakdown.items():
        total = counts["positive"] + counts["negative"] + counts["neutral"]
        if total == 0:
            continue
        results[aspect] = {
            "count": total,
            "positive": round(counts["positive"] / total, 4),
            "negative": round(counts["negative"] / total, 4),
            "neutral": round(counts["neutral"] / total, 4),
            "avg_intensity": round(
                abs(counts["positive"] - counts["negative"]) / total, 4
            ),
        }
    return results


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — LLM Insights
# Cerebras (qwen-3-235b-a22b-instruct-2507) primary → Groq (llama-3.3-70b) fallback
# ══════════════════════════════════════════════════════════════════════════════


async def node_generate_insights(state: AnalysisState) -> AnalysisState:
    logger.info("node_generate_insights_start", job_id=state["job_id"])

    dist = state["sentiment_distribution"]
    aspects = state["aspect_results"]
    brand = state["brand_name"]
    total = state["total_posts"]
    platform_breakdown = state["platform_breakdown"]

    top_negative = sorted(
        [p for p in state["analyzed_posts"] if p["sentiment"] == "negative"],
        key=lambda x: x.get("negative_score", 0),
        reverse=True,
    )[:5]

    negative_samples = (
        "\n".join(f'- "{p["combined_text"][:150]}..."' for p in top_negative)
        or "None found."
    )

    aspect_summary = (
        "\n".join(
            f"   - {aspect}: {data['count']} mentions, "
            f"{data['positive'] * 100:.0f}% positive, {data['negative'] * 100:.0f}% negative"
            for aspect, data in aspects.items()
        )
        or "   No aspect data available."
    )

    prompt = f"""You are a brand intelligence analyst. Analyze this data and provide actionable insights.

BRAND: {brand}
TOTAL POSTS ANALYZED: {total}
PLATFORMS: {platform_breakdown}

SENTIMENT DISTRIBUTION:
- Positive: {dist["positive"] * 100:.1f}%
- Negative: {dist["negative"] * 100:.1f}%
- Neutral:  {dist["neutral"] * 100:.1f}%

ASPECT BREAKDOWN:
{aspect_summary}

TOP NEGATIVE POSTS (sample):
{negative_samples}

Provide a concise brand intelligence report with:
1. SUMMARY: 2-3 sentences on overall brand sentiment
2. KEY THEMES: 3-5 bullet points on what people discuss most
3. CONCERNS: Top 2-3 specific concerns from negative posts
4. RECOMMENDATIONS: 2-3 actionable steps for the brand

Keep it factual, specific, and under 300 words total."""

    summary = None
    themes = []
    recommendations = []

    # ── Primary: Cerebras qwen-3-235b-a22b-instruct-2507 ──────────────────────────────────────
    cerebras_key = getattr(settings, "cerebras_api_key", None)
    if cerebras_key:
        try:
            client = AsyncOpenAI(
                api_key=cerebras_key,
                base_url="https://api.cerebras.ai/v1",
            )
            response = await client.chat.completions.create(
                model="qwen-3-235b-a22b-instruct-2507",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=500,
            )
            summary = response.choices[0].message.content
            themes = _extract_bullet_section(summary, "KEY THEMES")
            recommendations = _extract_bullet_section(summary, "RECOMMENDATIONS")
            logger.info(
                "cerebras_insight_done",
                job_id=state["job_id"],
                model="qwen-3-235b-a22b-instruct-2507",
            )
        except Exception as e:
            logger.warning("cerebras_insight_failed", error=str(e))
            summary = None

    # ── Fallback: Groq llama-3.3-70b ────────────────────────────────────────
    if summary is None and settings.groq_api_key:
        try:
            llm = ChatGroq(
                api_key=settings.groq_api_key,
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                max_tokens=500,
            )
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            summary = response.content
            themes = _extract_bullet_section(summary, "KEY THEMES")
            recommendations = _extract_bullet_section(summary, "RECOMMENDATIONS")
            logger.info(
                "groq_insight_done",
                job_id=state["job_id"],
                model="llama-3.3-70b-versatile",
            )
        except Exception as e:
            logger.warning("groq_insight_failed", error=str(e))
            summary = None

    # ── Final fallback: statistical summary ─────────────────────────────────
    if summary is None:
        logger.warning("all_insight_providers_failed", job_id=state["job_id"])
        summary = _build_fallback_summary(state)

    logger.info("node_generate_insights_done", job_id=state["job_id"])

    return {
        **state,
        "insight_summary": summary,
        "key_themes": themes,
        "recommendations": recommendations,
        "current_node": "generate_insights",
    }


def _extract_bullet_section(text: str, section_name: str) -> list[str]:
    lines = text.split("\n")
    in_section = False
    bullets = []
    for line in lines:
        if section_name in line.upper():
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith(("-", "•", "*", "·")):
                bullets.append(stripped.lstrip("-•*· ").strip())
            elif stripped and not stripped[0].isdigit() and bullets:
                break
    return bullets[:5]


def _build_fallback_summary(state: AnalysisState) -> str:
    dist = state["sentiment_distribution"]
    brand = state["brand_name"]
    total = state["total_posts"]
    dominant = max(dist, key=lambda k: dist[k])
    return (
        f"Analysis of {total} posts about {brand} shows "
        f"{dist['positive'] * 100:.1f}% positive, "
        f"{dist['negative'] * 100:.1f}% negative, and "
        f"{dist['neutral'] * 100:.1f}% neutral sentiment. "
        f"Overall brand perception is {dominant}."
    )


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — Crisis Detection
# ══════════════════════════════════════════════════════════════════════════════


def node_detect_crisis(state: AnalysisState) -> AnalysisState:
    logger.info("node_detect_crisis_start", job_id=state["job_id"])

    dist = state["sentiment_distribution"]
    neg_pct = dist.get("negative", 0.0)

    CRISIS_THRESHOLD = 0.60
    CONCERN_THRESHOLD = 0.40

    crisis_score = neg_pct / CRISIS_THRESHOLD
    crisis_triggered = crisis_score >= 1.0

    worst_aspect = None
    worst_neg = 0.0
    for aspect, data in state.get("aspect_results", {}).items():
        if data["negative"] > worst_neg:
            worst_neg = data["negative"]
            worst_aspect = aspect

    top_concern = (
        f"High negativity around '{worst_aspect}' ({worst_neg * 100:.0f}% negative)"
        if worst_aspect
        else None
    )

    crisis_details = {
        "negative_percentage": round(neg_pct * 100, 1),
        "crisis_threshold_pct": CRISIS_THRESHOLD * 100,
        "concern_threshold_pct": CONCERN_THRESHOLD * 100,
        "is_concern": neg_pct >= CONCERN_THRESHOLD,
        "top_concern": top_concern,
    }

    if crisis_triggered:
        logger.warning(
            "crisis_detected",
            job_id=state["job_id"],
            brand=state["brand_name"],
            crisis_score=round(crisis_score, 3),
            neg_pct=round(neg_pct * 100, 1),
        )
    else:
        logger.info(
            "no_crisis", job_id=state["job_id"], crisis_score=round(crisis_score, 3)
        )

    return {
        **state,
        "crisis_score": round(crisis_score, 4),
        "crisis_triggered": crisis_triggered,
        "crisis_details": crisis_details,
        "current_node": "detect_crisis",
    }
