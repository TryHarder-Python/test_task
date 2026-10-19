from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration, read from environment variables (or a local `.env`)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Defaults match docker-compose so the service runs locally against `docker compose up db`.
    database_url: str = "postgresql+asyncpg://cache:cache@localhost:5432/cache"
    transformer_delay_seconds: float = Field(default=0.1, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
