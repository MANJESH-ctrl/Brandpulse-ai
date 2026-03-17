from abc import ABC, abstractmethod
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaseCollector(ABC):
    EMOTIONAL_INDICATORS = [
        "love",
        "hate",
        "best",
        "worst",
        "awesome",
        "terrible",
        "amazing",
        "awful",
        "disappointing",
        "brilliant",
        "rubbish",
        "fantastic",
        "horrible",
        "perfect",
        "broken",
        "waste",
        "recommend",
        "avoid",
        "regret",
        "sucks",
        "great",
        "bad",
        "excellent",
        "poor",
        "beautiful",
        "ugly",
        "fast",
        "slow",
        "easy",
        "difficult",
        "worth it",
        "overpriced",
        "cheap",
        "expensive",
        "happy",
        "sad",
        "angry",
        "frustrated",
        "delighted",
        "disgusted",
        "pleased",
        "annoyed",
        "satisfied",
        "unsatisfied",
        "issue",
        "problem",
        "bug",
        "crash",
    ]

    def __init__(self, platform: str):
        self.platform = platform
        self.logger = get_logger(f"collector.{platform}")

    @abstractmethod
    async def collect(
        self,
        brand_name: str,
        keywords: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        pass

    def _build_query(
        self,
        brand_name: str,
        keywords: str = "",
        include_emotional: bool = True,
    ) -> str:
        parts = [f'"{brand_name}"']
        if keywords:
            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
            if kw_list:
                parts.append(f"({' OR '.join(kw_list)})")
        if include_emotional:
            emotional = " OR ".join(self.EMOTIONAL_INDICATORS[:15])
            parts.append(f"({emotional})")
        return " AND ".join(parts)

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        return " ".join(text.split())

    def _make_post(self, **kwargs) -> dict[str, Any]:
        return {
            "id": kwargs.get("post_id", kwargs.get("id", "")),  # ← FIXED
            "platform": self.platform,
            "brand_name": kwargs.get("brand_name", ""),
            "title": self._clean_text(kwargs.get("title", "")),
            "text": self._clean_text(kwargs.get("text", "")),
            "platform_meta": kwargs.get("platform_meta", {}),
        }
