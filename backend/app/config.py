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
    alpaca_api_key: str | None = None
    alpaca_api_secret: str | None = None
    alpaca_data_feed: str = "iex"
    alpaca_watchlist_limit: int = 20
    snapshot_interval_minutes: int = 15
    history_sync_interval_minutes: int = 1
    news_enabled: bool = True
    news_evening_hour_et: int = 20
    news_evening_minute_et: int = 30
    news_morning_hour_et: int = 8
    news_morning_minute_et: int = 55
    news_ir_feeds_json: str = "{}"
    news_ir_event_feeds_json: str = "{}"
    news_exposures_json: str = "{}"
    news_rss_feeds_json: str = "{}"
    sec_user_agent: str | None = None
    alpha_vantage_api_key: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"


settings = Settings()
