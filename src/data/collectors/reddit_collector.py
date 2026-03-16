import asyncpraw
from typing import Any
from src.data.collectors.base_collector import BaseCollector
from src.utils.config import settings


class RedditCollector(BaseCollector):
    """
    Async Reddit collector using asyncpraw.
    Tries 3 query strategies from specific → broad so we always
    get data even for niche brands.
    """

    def __init__(self):
        super().__init__("reddit")

    async def collect(
        self,
        brand_name: str,
        keywords: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:

        strategies = [
            self._build_query(brand_name, keywords, include_emotional=True),
            self._build_query(brand_name, keywords, include_emotional=False),
            f'"{brand_name}"',
        ]

        collected: list[dict[str, Any]] = []

        async with asyncpraw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        ) as reddit:

            for query in strategies:
                if len(collected) >= limit:
                    break

                try:
                    self.logger.info("reddit_strategy", query=query)
                    subreddit = await reddit.subreddit("all")

                    async for submission in subreddit.search(
                        query,
                        sort="relevance",
                        time_filter="year",
                        limit=limit - len(collected),
                    ):
                        post = self._make_post(
                            brand_name=brand_name,
                            post_id=submission.id,        
                            title=submission.title,
                            text=submission.selftext,
                            platform_meta={
                                "score":        submission.score,
                                "upvotes":      submission.ups,
                                "num_comments": submission.num_comments,
                                "subreddit":    str(submission.subreddit),
                                "url":          submission.url,
                            },
                        )

                        if post["title"] or post["text"]:
                            collected.append(post)

                except Exception as e:
                    self.logger.warning("reddit_strategy_failed", error=str(e))
                    continue

        self.logger.info("reddit_collected", brand=brand_name, count=len(collected))
        return collected
