# src/utils/config.py
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────────────
    app_name: str = "BrandPulse AI"
    app_version: str = "0.2.0"
    debug: bool = False
    log_level: str = "INFO" 

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str 

    # ── Groq ──────────────────────────────────────────────────────────────────
    groq_api_key: str
    groq_model_fast: str = "llama-3.1-8b-instant"
    sentiment_model: str = "groq/llama-3.3-70b-versatile"

    # ── Cerebras (optional — sentiment fallback) ──────────────────────────────
    cerebras_api_key: Optional[str] = None

    # ── Reddit ────────────────────────────────────────────────────────────────
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str = "BrandPulse/0.2.0"

    # ── YouTube ───────────────────────────────────────────────────────────────
    youtube_api_key: str

    # ── Pipeline ──────────────────────────────────────────────────────────────
    max_posts_per_platform: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton — imported as `from src.utils.config import settings`
settings = get_settings()
