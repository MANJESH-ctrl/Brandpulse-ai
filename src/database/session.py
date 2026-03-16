from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from typing import AsyncGenerator
from src.utils.config import settings
from src.database.models import Base
from src.utils.logger import get_logger

logger = get_logger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,   
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables. Called once on app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))
    logger.info("database_initialized", url=settings.database_url)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields a session per request.
    Commits on success, rolls back on any exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
