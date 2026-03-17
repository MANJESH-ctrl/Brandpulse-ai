from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import CrisisAlertResponse
from src.database.models import CrisisAlert
from src.database.session import get_db
from src.utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["Crisis"])
logger = get_logger(__name__)


@router.get("/alerts", response_model=list[CrisisAlertResponse])
async def get_crisis_alerts(
    brand_name: str | None = None,
    unacknowledged_only: bool = False,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    query = select(CrisisAlert).order_by(desc(CrisisAlert.triggered_at)).limit(limit)
    if brand_name:
        query = query.where(CrisisAlert.brand_name == brand_name)
    if unacknowledged_only:
        query = query.where(CrisisAlert.is_acknowledged == 0)
    result = await db.execute(query)
    alerts = result.scalars().all()
    return [
        CrisisAlertResponse(
            id=a.id,
            brand_name=a.brand_name,
            triggered_at=a.triggered_at.isoformat(),
            spike_percentage=a.spike_percentage or 0.0,
            current_score=a.current_score or 0.0,
            top_concern=a.top_concern,
            is_acknowledged=bool(a.is_acknowledged),
        )
        for a in alerts
    ]


@router.patch("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CrisisAlert).where(CrisisAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    alert.is_acknowledged = 1
    await db.commit()
    return {"alert_id": alert_id, "acknowledged": True}
