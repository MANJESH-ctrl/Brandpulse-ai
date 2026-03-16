import httpx
from typing import Any
from src.data.collectors.base_collector import BaseCollector
from src.utils.config import settings

_YT_SEARCH   = "https://www.googleapis.com/youtube/v3/search"
_YT_VIDEOS   = "https://www.googleapis.com/youtube/v3/videos"
_YT_COMMENTS = "https://www.googleapis.com/youtube/v3/commentThreads"


class YouTubeCollector(BaseCollector):
    """
    Async YouTube collector using httpx directly against the
    YouTube Data API v3. Batches video-details calls to save quota.
    """

    def __init__(self):
        super().__init__("youtube")

    async def collect(
        self,
        brand_name: str,
        keywords: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:

        if not settings.youtube_api_key:
            self.logger.warning("youtube_api_key_missing")
            return []

        strategies = [
            self._build_query(brand_name, keywords, include_emotional=True),
            self._build_query(brand_name, keywords, include_emotional=False),
            brand_name,
        ]

        collected: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for query in strategies:
                if len(collected) >= limit:
                    break

                try:
                    self.logger.info("youtube_strategy", query=query)
                    video_ids = await self._search_videos(client, query, limit)

                    if not video_ids:
                        continue

                    videos   = await self._get_video_details(client, video_ids, brand_name)
                    comments = await self._get_comments(client, video_ids[:5], brand_name)

                    collected.extend(videos)
                    collected.extend(comments)

                except Exception as e:
                    self.logger.warning("youtube_strategy_failed", error=str(e))
                    continue

        self.logger.info("youtube_collected", brand=brand_name, count=len(collected))
        return collected[:limit]

    async def _search_videos(
        self,
        client: httpx.AsyncClient,
        query: str,
        limit: int,
    ) -> list[str]:
        resp = await client.get(_YT_SEARCH, params={
            "q":          query,
            "part":       "snippet",
            "type":       "video",
            "maxResults": min(limit, 50),
            "order":      "relevance",
            "key":        settings.youtube_api_key,
        })
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [i["id"]["videoId"] for i in items]

    async def _get_video_details(
        self,
        client: httpx.AsyncClient,
        video_ids: list[str],
        brand_name: str,
    ) -> list[dict[str, Any]]:
        resp = await client.get(_YT_VIDEOS, params={
            "id":   ",".join(video_ids),
            "part": "snippet,statistics",
            "key":  settings.youtube_api_key,
        })
        resp.raise_for_status()

        posts = []
        for item in resp.json().get("items", []):
            snippet = item.get("snippet",    {})
            stats   = item.get("statistics", {})
            post = self._make_post(
                brand_name=brand_name,
                post_id=item["id"],                              
                title=snippet.get("title", ""),
                text=snippet.get("description", ""),
                platform_meta={
                    "video_id":      item["id"],
                    "views":         int(stats.get("viewCount",    0) or 0),  
                    "likes":         int(stats.get("likeCount",    0) or 0),  
                    "comments_count":int(stats.get("commentCount", 0) or 0),  
                    "content_type":  "video",
                },
            )
            if post["title"] or post["text"]:
                posts.append(post)
        return posts

    async def _get_comments(
        self,
        client: httpx.AsyncClient,
        video_ids: list[str],
        brand_name: str,
    ) -> list[dict[str, Any]]:
        comments = []
        for vid_id in video_ids:
            try:
                resp = await client.get(_YT_COMMENTS, params={
                    "videoId":    vid_id,
                    "part":       "snippet",
                    "maxResults": 10,
                    "order":      "relevance",
                    "key":        settings.youtube_api_key,
                })
                resp.raise_for_status()
                for item in resp.json().get("items", []):
                    c    = item["snippet"]["topLevelComment"]["snippet"]
                    post = self._make_post(
                        brand_name=brand_name,
                        post_id=item["id"],                      
                        title="",
                        text=c.get("textDisplay", ""),
                        platform_meta={
                            "video_id":     vid_id,
                            "likes":        int(c.get("likeCount", 0) or 0),
                            "content_type": "comment",
                        },
                    )
                    if post["text"]:
                        comments.append(post)
            except Exception:
                continue
        return comments
