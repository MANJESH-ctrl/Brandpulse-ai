import httpx
from typing import Any
from src.data.collectors.base_collector import BaseCollector

_HN_SEARCH = "https://hn.algolia.com/api/v1/search"


class HackerNewsCollector(BaseCollector):
    """
    Async HackerNews collector via Algolia API.
    Requires zero API keys — completely free and open.
    HN is critical for tech brands: developers post honest opinions here.
    """

    def __init__(self):
        super().__init__("hackernews")

    async def collect(
        self,
        brand_name: str,
        keywords: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:

        collected: list[dict[str, Any]] = []

        tag_strategies = [
            ("story",   limit // 2),
            ("comment", limit // 2),
        ]

        async with httpx.AsyncClient(timeout=20.0) as client:
            for tag, per_limit in tag_strategies:
                try:
                    query = f"{brand_name}"
                    if keywords:
                        query += f" {keywords.split(',')[0].strip()}"

                    resp = await client.get(_HN_SEARCH, params={
                        "query":       query,
                        "tags":        tag,
                        "hitsPerPage": per_limit,
                    })
                    resp.raise_for_status()

                    for hit in resp.json().get("hits", []):
                        text  = hit.get("comment_text") or hit.get("story_text") or ""
                        title = hit.get("title") or hit.get("story_title") or ""

                        post = self._make_post(
                            brand_name=brand_name,
                            post_id=hit.get("objectID", ""),     # ← FIXED
                            title=title,
                            text=text,
                            platform_meta={
                                "hn_id":        hit.get("objectID"),
                                "points":       hit.get("points", 0),
                                "num_comments": hit.get("num_comments", 0),
                                "author":       hit.get("author", ""),
                                "content_type": tag,
                                "url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                            },
                        )

                        if post["title"] or len(post["text"]) > 20:
                            collected.append(post)

                except Exception as e:
                    self.logger.warning("hn_collection_failed", tag=tag, error=str(e))
                    continue

        self.logger.info("hn_collected", brand=brand_name, count=len(collected))
        return collected
