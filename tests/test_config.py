"""
Unit tests for config/startup safety.
Tests that missing required env vars raise ValidationError.
Uses _env_file=None to prevent pydantic-settings from reading the real .env.
"""

import os
import pytest
from unittest.mock import patch
from pydantic import ValidationError


class TestMissingGroqKey:
    def test_missing_groq_api_key_raises(self):
        """Settings must fail if GROQ_API_KEY is not set."""
        env = {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "REDDIT_CLIENT_ID": "x",
            "REDDIT_CLIENT_SECRET": "x",
            "YOUTUBE_API_KEY": "x",
        }
        with patch.dict(os.environ, env, clear=True):
            from src.utils.config import Settings

            with pytest.raises(ValidationError):
                Settings(_env_file=None)


class TestMissingDatabaseUrl:
    def test_missing_database_url_raises(self):
        """Settings must fail if DATABASE_URL is not set."""
        env = {
            "GROQ_API_KEY": "x",
            "REDDIT_CLIENT_ID": "x",
            "REDDIT_CLIENT_SECRET": "x",
            "YOUTUBE_API_KEY": "x",
        }
        with patch.dict(os.environ, env, clear=True):
            from src.utils.config import Settings

            with pytest.raises(ValidationError):
                Settings(_env_file="nonexistent_file_that_doesnt_exist.env")


class TestDefaultValues:
    def test_defaults_load_correctly(self):
        """When all required keys are present, defaults should be sane."""
        env = {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "GROQ_API_KEY": "test-key",
            "REDDIT_CLIENT_ID": "test-id",
            "REDDIT_CLIENT_SECRET": "test-secret",
            "YOUTUBE_API_KEY": "test-yt",
        }
        with patch.dict(os.environ, env, clear=True):
            from src.utils.config import Settings

            s = Settings(_env_file=None)
            assert s.app_name == "BrandPulse AI"
            assert s.app_version == "0.2.0"
            assert s.debug is False
            assert s.log_level == "INFO"
            assert s.max_posts_per_platform == 100
            assert s.reddit_user_agent == "BrandPulse/0.2.0"
            assert s.cerebras_api_key is None
