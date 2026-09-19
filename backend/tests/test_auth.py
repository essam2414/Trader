"""Tests for API authentication and authorization.

Verifies that the require_api_key dependency correctly validates bearer tokens
against the configured dashboard API key to gate access to protected routes.
"""

import pytest
from fastapi import HTTPException

from app import config
from app.auth import require_api_key


def test_require_api_key_accepts_matching_bearer_token(monkeypatch):
    """require_api_key should not raise when given a matching bearer token."""
    monkeypatch.setattr(config.settings, "dashboard_api_key", "expected-secret")

    require_api_key(authorization="Bearer expected-secret")  # should not raise


def test_require_api_key_rejects_wrong_token(monkeypatch):
    """require_api_key should raise 401 when token does not match."""
    monkeypatch.setattr(config.settings, "dashboard_api_key", "expected-secret")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(authorization="Bearer wrong-secret")

    assert exc_info.value.status_code == 401


def test_require_api_key_rejects_missing_token(monkeypatch):
    """require_api_key should raise 401 when authorization header is missing."""
    monkeypatch.setattr(config.settings, "dashboard_api_key", "expected-secret")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(authorization="")

    assert exc_info.value.status_code == 401
