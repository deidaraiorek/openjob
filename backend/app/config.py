from functools import lru_cache
from pathlib import Path

REPO_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "OpenJob API"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/openjob"
    redis_url: str = "redis://localhost:6379/0"
    owner_email: str = "owner@example.com"
    owner_password: str = "changeme"
    session_secret: str = "replace-me"
    secure_cookies: bool = False
    playwright_profile_dir: str = "/tmp/openjob-playwright"
    playwright_artifact_dir: str = "/tmp/openjob-playwright-artifacts"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    relevance_retry_attempts: int = 2
    relevance_retry_base_delay_seconds: float = 0.5
    openai_api_key: str | None = None
    openai_role_profile_model: str = "gpt-5-mini"
    openai_job_relevance_model: str = "gpt-5-mini"

    @property
    def session_cookie_name(self) -> str:
        return "openjob_session"


@lru_cache
def get_settings() -> Settings:
    return Settings()
