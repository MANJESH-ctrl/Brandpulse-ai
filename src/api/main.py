from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.utils.config import settings
from src.utils.logger import setup_logging, get_logger
from src.database.session import init_db
from src.api.routers.analysis import router as analysis_router
from src.api.routers.results import router as results_router  # ← ADD
from src.api.routers.brands import router as brands_router

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from src.api.routers.alerts import router as alerts_router


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    # ── Startup ──────────────────────────────
    setup_logging()
    await init_db()
    logger.info(
        "brandpulse_started",
        app=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )
    yield
    # ── Shutdown ─────────────────────────────
    logger.info("brandpulse_stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered brand intelligence platform — zero cost, full production stack.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router)
app.include_router(results_router)
app.include_router(brands_router)
app.include_router(alerts_router)

# Serve frontend static assets
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/ui", include_in_schema=False)
async def serve_ui():
    return FileResponse("frontend/index.html")


@app.get("/", include_in_schema=False)
async def root_redirect():
    return FileResponse("frontend/index.html")


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Used by load balancers, Docker, and monitoring systems.
    """
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "debug": settings.debug,
        "database": settings.database_url.split(":")[
            0
        ],  # shows "sqlite" or "postgresql"
    }
