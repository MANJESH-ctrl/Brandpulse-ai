from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import FullAnalysisResult
from src.database.models import (
    AnalysisJob,
    AnalysisResult,
    CollectedPost,
    JobStatus,
)
from src.database.session import get_db
from src.utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["Results"])
logger = get_logger(__name__)


@router.get("/results/{job_id}", response_model=FullAnalysisResult)
async def get_analysis_result(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the full analysis result for a completed job.
    Returns sentiment distribution, aspect breakdown, insights, crisis score.
    """
    # Fetch job
    job_result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not complete yet. Current status: {job.status}",
        )

    # Fetch result
    result_query = await db.execute(
        select(AnalysisResult).where(AnalysisResult.job_id == job_id)
    )
    result = result_query.scalar_one_or_none()
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Analysis result not found. Job may have failed during processing.",
        )

    dist = result.sentiment_distribution or {}
    crisis_score = result.crisis_score or 0.0
    crisis_triggered = crisis_score >= 1.0

    return FullAnalysisResult(
        job_id=job_id,
        brand_name=result.brand_name,
        status=job.status,
        post_count=result.post_count or 0,
        platform_breakdown=result.platform_breakdown or {},
        sentiment_distribution=dist,
        weighted_sentiment=result.weighted_sentiment or {},
        aspect_results=result.aspect_results or {},
        insight_summary=result.insight_summary,
        crisis_score=round(crisis_score, 4),
        crisis_triggered=crisis_triggered,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.get("/results/{job_id}/posts/sentiment", tags=["Results"])
async def get_sentiment_breakdown_by_platform(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Per-platform sentiment breakdown for charts.
    Returns data ready for Streamlit bar/pie charts.
    """

    job_result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    posts_result = await db.execute(
        select(CollectedPost).where(CollectedPost.job_id == job_id)
    )
    posts = posts_result.scalars().all()

    # Build per-platform breakdown
    breakdown: dict[str, dict] = {}
    for post in posts:
        platform = post.platform
        if platform not in breakdown:
            breakdown[platform] = {
                "positive": 0,
                "negative": 0,
                "neutral": 0,
                "total": 0,
            }
        if post.sentiment:
            breakdown[platform][post.sentiment] = (
                breakdown[platform].get(post.sentiment, 0) + 1
            )
            breakdown[platform]["total"] += 1

    # Compute percentages
    result = {}
    for platform, counts in breakdown.items():
        total = counts["total"]
        if total == 0:
            continue
        result[platform] = {
            "positive_pct": round(counts["positive"] / total * 100, 1),
            "negative_pct": round(counts["negative"] / total * 100, 1),
            "neutral_pct": round(counts["neutral"] / total * 100, 1),
            "total_posts": total,
        }

    return {
        "job_id": job_id,
        "brand_name": job.brand_name,
        "platform_sentiment": result,
    }
