# src/analysis/sentiment_analyzer.py
import asyncio
import json
import structlog
from groq import AsyncGroq
from typing import Dict, List, Optional


logger = structlog.get_logger()


SYSTEM_PROMPT = (
    "You are BrandPulse AI -- a brand sentiment intelligence engine.\n"
    "Analyze what social media posts say about a SPECIFIC brand.\n\n"
    "Nuance you must handle:\n"
    "- Sarcasm: Oh great, another outage! = NEGATIVE\n"
    "- Indirect: I returned my Tesla for a BMW = NEGATIVE for Tesla\n"
    "- Analytical: Apple M4 dominates benchmarks = POSITIVE\n"
    "- Off-topic: post barely mentions brand -> brand_relevance below 0.3\n\n"
    "Return ONLY valid JSON. No markdown, no explanation outside JSON."
)


USER_PROMPT = (
    "Brand: {brand_name}\n"
    "Platform: {platform}\n\n"
    "Analyze each post sentiment toward {brand_name} only.\n"
    "Ignore competitors and unrelated topics.\n\n"
    "Return JSON object with key results -- one item per post:\n"
    "{{\"results\": [{{\"post_id\": \"id\", \"sentiment\": \"positive|negative|neutral\","
    "\"confidence\": 0.1-1.0, \"is_sarcastic\": true|false,"
    "\"aspect\": \"product|pricing|service|leadership|ethics|performance|general\","
    "\"intensity\": \"mild|moderate|strong\", \"brand_relevance\": 0.0-1.0,"
    "\"reason\": \"max 12 words\"}}]}}\n\n"
    "Posts:\n{posts_json}"
)


class SentimentAnalyzer:
    PRIMARY_MODEL  = "qwen-3-235b-a22b-instruct-2507"           # Cerebras — primary
    FALLBACK_MODEL = "llama-3.3-70b-versatile"                  # Groq    — fallback
    BATCH_SIZE     = 12
    MAX_CHARS      = 500


    def __init__(self, groq_api_key: str, cerebras_api_key: Optional[str] = None):
        self.groq      = AsyncGroq(api_key=groq_api_key)
        self._cerebras = None
        if cerebras_api_key:
            try:
                from openai import AsyncOpenAI
                self._cerebras = AsyncOpenAI(
                    api_key=cerebras_api_key,
                    base_url="https://api.cerebras.ai/v1",
                )
            except ImportError:
                logger.warning("cerebras_skip", reason="openai package not installed")


    async def analyze(self, posts: List[Dict], brand_name: str) -> Dict:
        if not posts:
            return self._empty_result()

        primary = f"{self.PRIMARY_MODEL} (cerebras)" if self._cerebras else f"{self.FALLBACK_MODEL} (groq)"
        logger.info("llm_sentiment_start", brand=brand_name,
                    total=len(posts), model=primary)

        by_platform: Dict[str, List[Dict]] = {}
        for post in posts:
            by_platform.setdefault(post.get("platform", "unknown"), []).append(post)

        batches = [
            (plat_posts[i:i + self.BATCH_SIZE], platform)
            for platform, plat_posts in by_platform.items()
            for i in range(0, len(plat_posts), self.BATCH_SIZE)
        ]

        semaphore = asyncio.Semaphore(2)

        async def run(batch_data):
            async with semaphore:
                return await self._batch_with_fallback(*batch_data, brand_name=brand_name)

        nested      = await asyncio.gather(*[run(b) for b in batches])
        llm_results = [item for sub in nested for item in sub]
        return self._build_output(llm_results, posts, brand_name)


    async def _batch_with_fallback(
        self, posts: List[Dict], platform: str, brand_name: str
    ) -> List[Dict]:

        # ── Primary: Cerebras {self.PRIMARY_MODEL} ────────────────────────────────
        if self._cerebras:
            for attempt in range(4):
                try:
                    return await self._call_cerebras(posts, brand_name, platform)
                except Exception as e:
                    err = str(e)
                    if "429" in err and attempt < 3:
                        wait = (2 ** attempt) * 3   # 3s, 6s, 12s
                        logger.warning("cerebras_rate_limit_retry",
                                       attempt=attempt + 1, wait=wait)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("cerebras_failed_using_groq", error=err)
                    break   # non-429 error — go straight to Groq

        # ── Fallback: Groq {self.FALLBACK_MODEL} ──────────────────────────────────
        for attempt in range(4):
            try:
                return await self._call_groq(posts, brand_name, platform)
            except Exception as e:
                err = str(e)
                if "429" in err and attempt < 3:
                    wait = (2 ** attempt) * 3
                    logger.warning("groq_rate_limit_retry",
                                   attempt=attempt + 1, wait=wait)
                    await asyncio.sleep(wait)
                    continue
                logger.error("groq_failed_neutral_fallback", error=err)
                break

        # ── Last resort: neutral ───────────────────────────────────────────
        return self._neutral_fallback(posts)


    async def _call_cerebras(
        self, posts: List[Dict], brand_name: str, platform: str
    ) -> List[Dict]:
        resp = await self._cerebras.chat.completions.create(
            model=self.PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": USER_PROMPT.format(
                    brand_name=brand_name,
                    platform=platform,
                    posts_json=self._fmt(posts),
                )},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2500,
        )
        return json.loads(resp.choices[0].message.content).get("results", [])


    async def _call_groq(
        self, posts: List[Dict], brand_name: str, platform: str
    ) -> List[Dict]:
        resp = await self.groq.chat.completions.create(
            model=self.FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": USER_PROMPT.format(
                    brand_name=brand_name,
                    platform=platform,
                    posts_json=self._fmt(posts),
                )},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2500,
        )
        return json.loads(resp.choices[0].message.content).get("results", [])


    def _fmt(self, posts: List[Dict]) -> str:
        return json.dumps([
            {
                "post_id": p.get("id", ""),
                "text": (
                    p.get("combined_text")
                    or (
                        (p.get("title") or "")
                        + " "
                        + (p.get("text") or p.get("body") or p.get("content") or "")
                    ).strip()
                )[: self.MAX_CHARS],
            }
            for p in posts
        ], indent=2, ensure_ascii=False)


    def _neutral_fallback(self, posts: List[Dict]) -> List[Dict]:
        return [
            {
                "post_id":        p.get("id", ""),
                "sentiment":      "neutral",
                "confidence":     0.5,
                "is_sarcastic":   False,
                "aspect":         "general",
                "intensity":      "mild",
                "brand_relevance": 0.5,
                "reason":         "analysis unavailable",
            }
            for p in posts
        ]


    def _build_output(
        self, llm_results: List[Dict], original_posts: List[Dict], brand_name: str
    ) -> Dict:
        result_map = {r.get("post_id", ""): r for r in llm_results}
        relevant   = [r for r in llm_results if r.get("brand_relevance", 1.0) >= 0.3]
        total      = max(len(relevant), 1)

        pos = sum(1 for r in relevant if r["sentiment"] == "positive")
        neg = sum(1 for r in relevant if r["sentiment"] == "negative")
        neu = sum(1 for r in relevant if r["sentiment"] == "neutral")

        aspect_breakdown: Dict[str, Dict] = {}
        for r in relevant:
            asp = r.get("aspect", "general")
            aspect_breakdown.setdefault(asp, {"positive": 0, "negative": 0, "neutral": 0})
            aspect_breakdown[asp][r["sentiment"]] += 1

        enriched = []
        for post in original_posts:
            llm   = result_map.get(post.get("id", ""), {})
            sent  = llm.get("sentiment", "neutral")
            conf  = llm.get("confidence", 0.5)
            pos_s = conf if sent == "positive" else round((1 - conf) * 0.15, 4)
            neg_s = conf if sent == "negative" else round((1 - conf) * 0.15, 4)
            neu_s = conf if sent == "neutral"  else round((1 - conf) * 0.15, 4)
            enriched.append({
                **post,
                "sentiment":           sent,
                "confidence":          round(conf, 4),
                "positive_score":      round(pos_s, 4),
                "negative_score":      round(neg_s, 4),
                "neutral_score":       round(neu_s, 4),
                "emotional_intensity": round(abs(pos_s - neg_s), 4),
                "is_sarcastic":        llm.get("is_sarcastic", False),
                "aspect":              llm.get("aspect", "general"),
                "intensity":           llm.get("intensity", "mild"),
                "brand_relevance":     llm.get("brand_relevance", 0.5),
                "sentiment_reason":    llm.get("reason", ""),
                "sentiment_source":    "llm",
            })

        distribution = {
            "positive": round(pos / total, 4),
            "negative": round(neg / total, 4),
            "neutral":  round(neu / total, 4),
        }

        logger.info(
            "llm_sentiment_done",
            brand=brand_name,
            distribution=distribution,
            sarcasm_detected=sum(1 for r in relevant if r.get("is_sarcastic")),
            model=self.PRIMARY_MODEL,
        )

        return {
            "distribution":     distribution,
            "posts":            enriched,
            "aspect_breakdown": aspect_breakdown,
            "model_used":       self.PRIMARY_MODEL,
            "relevant_count":   len(relevant),
        }


    def _empty_result(self) -> Dict:
        return {
            "distribution":     {"positive": 0.0, "negative": 0.0, "neutral": 0.0},
            "posts":            [],
            "aspect_breakdown": {},
            "model_used":       self.PRIMARY_MODEL,
        }
