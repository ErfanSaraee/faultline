"""Application configuration management using Pydantic v2 Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = Field(default="faultline",
                          description="Service identifier")
    env: Literal["development", "testing", "staging", "production"] = Field(
        default="development",
        description="Runtime environment name",
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Minimum structured logging level",
    )
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="URL prefix for v1 HTTP API endpoints",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
