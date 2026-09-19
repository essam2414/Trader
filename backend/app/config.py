"""Application environment-based configuration settings.

This module defines the Settings class which loads configuration from environment
variables using Pydantic Settings. All required credentials and optional parameters
are defined here for the Trading212 portfolio dashboard backend.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Configures API credentials, database connection, and service parameters
    needed by the Trading212 portfolio dashboard backend.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    trading212_api_key: str
    trading212_api_secret: str
    trading212_base_url: str = "https://live.trading212.com/api/v0"
    database_url: str = "sqlite:///./dev.db"
    dashboard_api_key: str
    snapshot_interval_minutes: int = 15


settings = Settings()
