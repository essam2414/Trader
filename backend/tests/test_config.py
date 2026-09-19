"""Tests for application configuration settings."""
import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_requires_trading212_and_dashboard_credentials(monkeypatch):
    """Settings should fail validation when required credentials are missing."""
    monkeypatch.delenv("TRADING212_API_KEY", raising=False)
    monkeypatch.delenv("TRADING212_API_SECRET", raising=False)
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_loads_from_environment_with_defaults(monkeypatch):
    """Settings should load from environment variables and apply defaults."""
    monkeypatch.setenv("TRADING212_API_KEY", "key")
    monkeypatch.setenv("TRADING212_API_SECRET", "secret")
    monkeypatch.setenv("DASHBOARD_API_KEY", "dashboard-secret")
    # conftest.py sets a real DATABASE_URL env var (not via monkeypatch) for the
    # whole test session so app modules import cleanly; remove it here so this
    # test can verify the actual default value.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.trading212_api_key == "key"
    assert settings.trading212_api_secret == "secret"
    assert settings.dashboard_api_key == "dashboard-secret"
    assert settings.trading212_base_url == "https://live.trading212.com/api/v0"
    assert settings.database_url == "sqlite:///./dev.db"
    assert settings.snapshot_interval_minutes == 15
