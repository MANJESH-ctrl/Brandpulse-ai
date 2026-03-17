from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.api.schemas import BrandCompareResponse, BrandSummary
from src.database.models import AnalysisResult
from src.database.session import get_db
from src.utils.logger import get_logger

router = APIRouter(prefix="/api/brands", tags=["Brands"])
logger = get_logger(__name__)


@router.get("", response_model=list[BrandSummary])
async def list_brands(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AnalysisResult)
        .options(joinedload(AnalysisResult.job))
        .order_by(desc(AnalysisResult.created_at))
    )
    all_results = result.scalars().all()

    brand_map: dict[str, list[AnalysisResult]] = {}
    for r in all_results:
        brand_map.setdefault(r.brand_name, []).append(r)

    summaries = []
    for brand_name, results in brand_map.items():
        latest = results[0]

        pos_vals = [
            r.sentiment_distribution.get("positive", 0)
            for r in results
            if r.sentiment_distribution
        ]
        neg_vals = [
            r.sentiment_distribution.get("negative", 0)
            for r in results
            if r.sentiment_distribution
        ]
        neu_vals = [
            r.sentiment_distribution.get("neutral", 0)
            for r in results
            if r.sentiment_distribution
        ]

        avg_pos = round(sum(pos_vals) / len(pos_vals), 4) if pos_vals else 0.0
        avg_neg = round(sum(neg_vals) / len(neg_vals), 4) if neg_vals else 0.0
        avg_neu = round(sum(neu_vals) / len(neu_vals), 4) if neu_vals else 0.0

        latest_job = latest.job  # already loaded via joinedload — zero extra query

        summaries.append(
            BrandSummary(
                brand_name=brand_name,
                total_analyses=len(results),
                latest_analysis_at=latest_job.completed_at.isoformat()
                if latest_job and latest_job.completed_at
                else None,
                avg_positive=avg_pos,
                avg_negative=avg_neg,
                avg_neutral=avg_neu,
                latest_crisis_score=round(latest.crisis_score or 0.0, 4),
                total_posts_analyzed=sum(r.post_count or 0 for r in results),
            )
        )

    return sorted(summaries, key=lambda x: x.latest_analysis_at or "", reverse=True)


@router.post("/compare", response_model=BrandCompareResponse)
async def compare_brands(
    brand_names: list[str],
    db: AsyncSession = Depends(get_db),
):
    if len(brand_names) < 2:
        raise HTTPException(
            status_code=400, detail="Provide at least 2 brands to compare"
        )
    if len(brand_names) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 brands at once")

    comparison = []
    for brand in brand_names:
        result = await db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.brand_name == brand)
            .order_by(desc(AnalysisResult.created_at))
            .limit(1)
        )
        latest = result.scalar_one_or_none()

        if not latest:
            comparison.append(
                {
                    "brand_name": brand,
                    "available": False,
                    "message": f"No analysis found for '{brand}'.",
                }
            )
            continue

        dist = latest.sentiment_distribution or {}
        aspects = latest.aspect_results or {}

        comparison.append(
            {
                "brand_name": brand,
                "available": True,
                "post_count": latest.post_count or 0,
                "positive_pct": round(dist.get("positive", 0) * 100, 1),
                "negative_pct": round(dist.get("negative", 0) * 100, 1),
                "neutral_pct": round(dist.get("neutral", 0) * 100, 1),
                "crisis_score": round(latest.crisis_score or 0.0, 3),
                "crisis_triggered": bool(latest.crisis_triggered),
                "top_aspects": {
                    k: v
                    for k, v in sorted(
                        aspects.items(),
                        key=lambda x: x[1].get("count", 0),
                        reverse=True,
                    )[:3]
                },
                "analyzed_at": latest.created_at.isoformat(),
            }
        )

    return BrandCompareResponse(brands=brand_names, comparison=comparison)


@router.get("/{brand_name}", response_model=list[dict])
async def get_brand_history(
    brand_name: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisResult)
        .options(joinedload(AnalysisResult.job))
        .where(AnalysisResult.brand_name == brand_name)
        .order_by(desc(AnalysisResult.created_at))
        .limit(limit)
    )
    results = result.scalars().all()

    if not results:
        raise HTTPException(
            status_code=404, detail=f"No analyses found for brand '{brand_name}'"
        )

    history = []
    for r in results:
        job = r.job
        dist = r.sentiment_distribution or {}
        history.append(
            {
                "job_id": r.job_id,
                "brand_name": r.brand_name,
                "post_count": r.post_count,
                "positive": dist.get("positive", 0),
                "negative": dist.get("negative", 0),
                "neutral": dist.get("neutral", 0),
                "crisis_score": round(r.crisis_score or 0.0, 4),
                "platform_breakdown": r.platform_breakdown or {},
                "analyzed_at": job.completed_at.isoformat()
                if job and job.completed_at
                else None,
            }
        )

    return history


@router.get("/{brand_name}/trend", response_model=list[dict])
async def get_brand_trend(
    brand_name: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.brand_name == brand_name)
        .order_by(AnalysisResult.created_at)
    )
    results = result.scalars().all()

    if not results:
        raise HTTPException(status_code=404, detail=f"No data for '{brand_name}'")

    trend = []
    for r in results:
        dist = r.sentiment_distribution or {}
        trend.append(
            {
                "date": r.created_at.isoformat(),
                "positive": round(dist.get("positive", 0) * 100, 1),
                "negative": round(dist.get("negative", 0) * 100, 1),
                "neutral": round(dist.get("neutral", 0) * 100, 1),
                "post_count": r.post_count or 0,
                "crisis_score": round(r.crisis_score or 0.0, 3),
            }
        )

    return trend
