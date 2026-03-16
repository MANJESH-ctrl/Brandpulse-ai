import asyncio
import re
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.schemas import AnalyzeRequest, AnalyzeResponse, JobStatusResponse, PostsResponse
from src.database.models import AnalysisJob, CollectedPost, JobStatus
from src.database.session import get_db, AsyncSessionLocal
from src.data.collectors import RedditCollector, YouTubeCollector, HackerNewsCollector
from src.utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["Analysis"])
logger = get_logger(__name__)


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def start_analysis(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    job_id = str(uuid4())
    job = AnalysisJob(
        id=job_id,
        brand_name=request.brand_name.strip(),
        platforms=request.platforms,
        keywords=request.keywords,
        status=JobStatus.PENDING,
        progress_message="Job queued, starting soon...",
    )
    db.add(job)
    await db.commit()
    background_tasks.add_task(
        run_collection_pipeline,
        job_id,
        request.brand_name.strip(),
        request.platforms,
        request.keywords,
        request.limit_per_platform,
    )
    logger.info("analysis_job_created", job_id=job_id, brand=request.brand_name)
    return AnalyzeResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Analysis started for '{request.brand_name}'. Poll the status URL for progress.",
        poll_url=f"/api/status/{job_id}",
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return JobStatusResponse(
        job_id=job.id,
        brand_name=job.brand_name,
        status=job.status,
        progress_message=job.progress_message,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        error_message=job.error_message,
    )


@router.get("/posts/{job_id}", response_model=PostsResponse)
async def get_collected_posts(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    job_result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    posts_result = await db.execute(select(CollectedPost).where(CollectedPost.job_id == job_id))
    posts = posts_result.scalars().all()
    breakdown: dict[str, int] = {}
    for post in posts:
        breakdown[post.platform] = breakdown.get(post.platform, 0) + 1
    return PostsResponse(
        job_id=job_id,
        brand_name=job.brand_name,
        total_posts=len(posts),
        platform_breakdown=breakdown,
        posts=[
            {
                "id":                  p.id,
                "platform":            p.platform,
                "title":               p.title,
                "text":                p.text[:300] + "..." if p.text and len(p.text) > 300 else p.text,
                "sentiment":           p.sentiment,
                "confidence":          p.confidence,
                "positive_score":      p.positive_score,
                "negative_score":      p.negative_score,
                "neutral_score":       p.neutral_score,
                "emotional_intensity": p.emotional_intensity,
                "engagement_score":    p.engagement_score,
                "platform_meta":       p.platform_meta,
                "collected_at":        p.collected_at.isoformat(),
            }
            for p in posts
        ],
    )


# ── Background Pipeline ───────────────────────────────────────────────────────

async def _update_job(
    job_id: str,
    status: JobStatus,
    message: str,
    error: str | None = None,
    completed: bool = False,
) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = status
            job.progress_message = message
            if error:
                job.error_message = error
            if completed:
                job.completed_at = datetime.now(timezone.utc)
            await db.commit()


async def run_collection_pipeline(
    job_id: str,
    brand_name: str,
    platforms: list[str],
    keywords: str,
    limit: int,
) -> None:
    from src.agents import run_analysis_graph
    from src.database.models import AnalysisResult, CrisisAlert

    logger.info("pipeline_started", job_id=job_id, brand=brand_name, platforms=platforms)

    try:
        # ── Step 1: Collect ───────────────────────────────────────────────
        await _update_job(job_id, JobStatus.COLLECTING, f"Collecting from {', '.join(platforms)}...")

        collector_tasks = []
        if "reddit" in platforms:
            collector_tasks.append(RedditCollector().collect(brand_name, keywords, limit))
        if "youtube" in platforms:
            collector_tasks.append(YouTubeCollector().collect(brand_name, keywords, limit))
        if "hackernews" in platforms:
            collector_tasks.append(HackerNewsCollector().collect(brand_name, keywords, limit))

        results = await asyncio.gather(*collector_tasks, return_exceptions=True)

        all_posts: list[dict] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error("collector_failed", job_id=job_id, error=str(result))
            else:
                all_posts.extend(result)

        if not all_posts:
            await _update_job(
                job_id, JobStatus.FAILED,
                "No posts collected — check API keys or try a different brand name.",
                error="Zero posts collected",
                completed=True,
            )
            return

        # ── Step 2: Store raw posts ───────────────────────────────────────
        await _update_job(
            job_id, JobStatus.PROCESSING,
            f"Collected {len(all_posts)} posts. Running analysis...",
        )

        async with AsyncSessionLocal() as db:
            for post_data in all_posts:
                post = CollectedPost(
                    job_id=job_id,
                    source_id=post_data.get("id", ""),
                    brand_name=brand_name,
                    platform=post_data["platform"],
                    title=post_data.get("title", ""),
                    text=post_data.get("text", ""),
                    platform_meta=post_data.get("platform_meta", {}),
                )
                db.add(post)
            await db.commit()

        # ── Step 3: Run LangGraph analysis pipeline ───────────────────────
        await _update_job(
            job_id, JobStatus.ANALYZING,
            f"Analyzing {len(all_posts)} posts with AI pipeline...",
        )

        final_state = await run_analysis_graph(job_id, brand_name, all_posts)

        # ── Step 4: Update collected posts with sentiment scores ──────────
        async with AsyncSessionLocal() as db:
            posts_result = await db.execute(
                select(CollectedPost).where(CollectedPost.job_id == job_id)
            )
            db_posts = posts_result.scalars().all()

            # ID-based matching 
            analyzed_map = {
                p.get("id", ""): p
                for p in final_state.get("analyzed_posts", [])
            }

            for db_post in db_posts:
                analyzed = analyzed_map.get(db_post.source_id)
                if analyzed:
                    db_post.cleaned_text        = analyzed.get("combined_text", "")
                    db_post.sentiment           = analyzed.get("sentiment")
                    db_post.confidence          = analyzed.get("confidence")
                    db_post.positive_score      = analyzed.get("positive_score")
                    db_post.negative_score      = analyzed.get("negative_score")
                    db_post.neutral_score       = analyzed.get("neutral_score")
                    db_post.emotional_intensity = analyzed.get("emotional_intensity")
                    db_post.engagement_score    = analyzed.get("engagement_score")
                    db_post.is_sarcastic        = 1 if analyzed.get("is_sarcastic") else 0
                    db_post.aspect              = analyzed.get("aspect")
                    db_post.brand_relevance     = analyzed.get("brand_relevance")
                    db_post.intensity           = analyzed.get("intensity")
                    db_post.sentiment_reason    = analyzed.get("sentiment_reason")

            await db.commit()

        # ── Step 5: Save AnalysisResult ───────────────────────────────────
        async with AsyncSessionLocal() as db:
            analysis_result = AnalysisResult(
                job_id=job_id,
                brand_name=brand_name,
                sentiment_distribution=final_state.get("sentiment_distribution"),
                weighted_sentiment=None,
                aspect_results=final_state.get("aspect_results"),
                insight_summary=final_state.get("insight_summary"),
                crisis_score=final_state.get("crisis_score", 0.0),
                crisis_triggered=1 if final_state.get("crisis_triggered") else 0,
                post_count=final_state.get("total_posts", 0),
                platform_breakdown=final_state.get("platform_breakdown"),
            )
            db.add(analysis_result)

            # ── Step 6: Fire crisis alert if triggered ────────────────────
            if final_state.get("crisis_triggered"):
                details = final_state.get("crisis_details", {})
                alert = CrisisAlert(
                    brand_name=brand_name,
                    spike_percentage=details.get("negative_percentage", 0),
                    baseline_score=details.get("concern_threshold_pct", 40),
                    current_score=details.get("negative_percentage", 0),
                    top_concern=details.get("top_concern"),
                )
                db.add(alert)
                logger.warning("crisis_alert_saved", job_id=job_id, brand=brand_name)

            await db.commit()

        # ── Step 7: Mark job done ─────────────────────────────────────────
        dist = final_state.get("sentiment_distribution", {})
        progress_msg = (
            f"Analysis complete — {final_state.get('total_posts', 0)} posts. "
            f"Sentiment: {dist.get('positive', 0)*100:.0f}% positive, "
            f"{dist.get('negative', 0)*100:.0f}% negative."
        )
        if final_state.get("crisis_triggered"):
            progress_msg += " ⚠️ Crisis alert triggered."

        await _update_job(job_id, JobStatus.DONE, progress_msg, completed=True)

        logger.info(
            "pipeline_complete",
            job_id=job_id,
            brand=brand_name,
            total_posts=final_state.get("total_posts"),
            crisis=final_state.get("crisis_triggered"),
        )

    except Exception as e:
        logger.error("pipeline_crashed", job_id=job_id, error=str(e), exc_info=True)
        await _update_job(
            job_id, JobStatus.FAILED,
            f"Pipeline failed: {str(e)}",
            error=str(e),
            completed=True,
        )
