"""
Shared fixtures for BrandPulse AI tests.

Sets fake env vars BEFORE any src module is imported, so pydantic-settings
never complains about missing keys. Then builds an in-memory SQLite DB and
a FastAPI TestClient.
"""

import os, sys

# ── Fake env vars — must happen before ANY src import ────────────────────────
_FAKE_ENV = {
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "GROQ_API_KEY": "test-groq-key",
    "REDDIT_CLIENT_ID": "test-reddit-id",
    "REDDIT_CLIENT_SECRET": "test-reddit-secret",
    "REDDIT_USER_AGENT": "test-agent",
    "YOUTUBE_API_KEY": "test-yt-key",
}
for k, v in _FAKE_ENV.items():
    os.environ.setdefault(k, v)

# Clear the lru_cache so Settings re-reads env vars
from src.utils.config import get_settings

get_settings.cache_clear()

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database.models import Base
from src.api.main import app
from src.database.session import get_db


# ── In-memory async engine shared across the test session ────────────────────
_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSession = async_sessionmaker(
    bind=_test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(autouse=True)
async def _setup_db():
    """Create tables before each test, drop after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_db():
    async with _TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
async def client():
    """Async test client hitting the real FastAPI app with mocked DB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def db_session():
    """Raw async session for seeding data in tests."""
    return _TestSession
