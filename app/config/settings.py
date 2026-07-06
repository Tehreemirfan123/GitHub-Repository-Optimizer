"""Settings for the Phase 1 Google ADK application."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loads project settings from app/.env."""

    github_token: SecretStr | None = Field(
        default=None,
        description="Optional read-only GitHub token for higher API limits.",
    )

    model_config = SettingsConfigDict(
        env_file="app/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: SecretStr = Field(
        description="Gemini API key used by Google ADK."
    )
    gemini_model: str = Field(
        default="gemini-flash-latest",
        min_length=1,
    )
    app_name: str = Field(
        default="github_repository_optimizer",
        min_length=1,
    )

    def validate_api_key(self) -> None:
        """Raise a clear error if the Gemini key is blank."""
        if not self.google_api_key.get_secret_value().strip():
            raise ValueError(
                "GOOGLE_API_KEY is empty. Add a valid Gemini API key to app/.env."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    settings = Settings()
    settings.validate_api_key()
    return settings