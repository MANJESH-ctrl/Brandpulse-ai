"""
Integration tests for every FastAPI endpoint.
All mocked — no real DB rows, no real pipeline. Fast.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

from src.database.models import AnalysisJob, AnalysisResult, CrisisAlert, CollectedPost, JobStatus


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_job(db_session, *, status=JobStatus.DONE, brand="TestBrand"):
    """Insert a complete job + result so GET endpoints have data."""
    Session = db_session
    job_id = str(uuid4())
    now = datetime.now(timezone.utc)

    async with Session() as s:
        job = AnalysisJob(
            id=job_id,
            brand_name=brand,
            platforms=["reddit"],
            status=status,
            progress_message="done",
            created_at=now,
            completed_at=now if status == JobStatus.DONE else None,
        )
        s.add(job)
        await s.flush()

        result = AnalysisResult(
            job_id=job_id,
            brand_name=brand,
            sentiment_distribution={"positive": 0.5, "negative": 0.2, "neutral": 0.3},
            aspect_results={"product": {"count": 10, "positive": 0.6, "negative": 0.2, "neutral": 0.2, "avg_intensity": 0.4}},
            insight_summary="Test insight",
            crisis_score=0.3,
            crisis_triggered=0,
            post_count=10,
            platform_breakdown={"reddit": 10},
            model_used="test-model",
        )
        s.add(result)
        await s.commit()
    return job_id


async def _seed_alert(db_session, *, brand="TestBrand"):
    Session = db_session
    async with Session() as s:
        alert = CrisisAlert(
            brand_name=brand,
            spike_percentage=15.0,
            baseline_score=10.0,
            current_score=25.0,
            top_concern="pricing complaints",
            is_acknowledged=0,
        )
        s.add(alert)
        await s.commit()
        return alert.id


# ── POST /api/analyze ────────────────────────────────────────────────────────

class TestPostAnalyze:
    from unittest.mock import patch, AsyncMock

    async def test_returns_202_with_job_id(self, client):
        with patch(
            "src.api.routers.analysis.run_collection_pipeline",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post("/api/analyze", json={
                "brand_name": "Nike",
                "platforms": ["reddit"],
            })
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert len(body["job_id"]) == 36  # UUID format

    async def test_empty_brand_name_rejected(self, client):
        resp = await client.post("/api/analyze", json={
            "brand_name": "   ",
            "platforms": ["reddit"],
        })
        assert resp.status_code == 422

    async def test_invalid_platform_rejected(self, client):
        resp = await client.post("/api/analyze", json={
            "brand_name": "Nike",
            "platforms": ["tiktok"],
        })
        assert resp.status_code == 422


# ── GET /api/status/{id} ─────────────────────────────────────────────────────

class TestGetStatus:
    async def test_404_on_unknown_job(self, client):
        fake_id = str(uuid4())
        resp = await client.get(f"/api/status/{fake_id}")
        assert resp.status_code == 404

    async def test_returns_status_for_existing_job(self, client, db_session):
        job_id = await _seed_job(db_session)
        resp = await client.get(f"/api/status/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job_id
        assert body["status"] == "done"
        assert body["brand_name"] == "TestBrand"


# ── GET /api/results/{id} ────────────────────────────────────────────────────

class TestGetResults:
    async def test_404_on_unknown_job(self, client):
        fake_id = str(uuid4())
        resp = await client.get(f"/api/results/{fake_id}")
        assert resp.status_code == 404

    async def test_returns_full_result_for_done_job(self, client, db_session):
        job_id = await _seed_job(db_session)
        resp = await client.get(f"/api/results/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job_id
        assert "sentiment_distribution" in body
        assert "positive" in body["sentiment_distribution"]
        assert body["post_count"] == 10
        assert body["crisis_triggered"] is False

    async def test_400_on_pending_job(self, client, db_session):
        job_id = await _seed_job(db_session, status=JobStatus.PENDING)
        resp = await client.get(f"/api/results/{job_id}")
        assert resp.status_code == 400


# ── GET /api/brands ──────────────────────────────────────────────────────────

class TestGetBrands:
    async def test_returns_200_list(self, client):
        resp = await client.get("/api/brands")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_returns_brand_after_seed(self, client, db_session):
        await _seed_job(db_session, brand="Apple")
        resp = await client.get("/api/brands")
        assert resp.status_code == 200
        brands = resp.json()
        assert len(brands) >= 1
        names = [b["brand_name"] for b in brands]
        assert "Apple" in names


# ── GET /api/alerts ──────────────────────────────────────────────────────────

class TestGetAlerts:
    async def test_returns_200_list(self, client):
        resp = await client.get("/api/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_returns_alert_after_seed(self, client, db_session):
        await _seed_alert(db_session, brand="Tesla")
        resp = await client.get("/api/alerts")
        assert resp.status_code == 200
        alerts = resp.json()
        assert len(alerts) >= 1
        assert alerts[0]["brand_name"] == "Tesla"


# ── PATCH /api/alerts/{id}/acknowledge ────────────────────────────────────────

class TestAcknowledgeAlert:
    async def test_404_on_unknown_alert(self, client):
        resp = await client.patch("/api/alerts/99999/acknowledge")
        assert resp.status_code == 404

    async def test_acknowledges_existing_alert(self, client, db_session):
        alert_id = await _seed_alert(db_session)
        resp = await client.patch(f"/api/alerts/{alert_id}/acknowledge")
        assert resp.status_code == 200
        body = resp.json()
        assert body["acknowledged"] is True


# ── GET /health ──────────────────────────────────────────────────────────────

class TestHealth:
    async def test_returns_200_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert "app" in body
        assert "version" in body
