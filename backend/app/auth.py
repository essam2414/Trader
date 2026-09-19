"""API authentication dependency for the portfolio dashboard.

This module provides a FastAPI dependency that gate-keeps protected API routes
behind a single shared-secret bearer token. Since this is a single-user personal
dashboard deployed to a public URL, this simple bearer token approach (validated
against settings.dashboard_api_key) is sufficient and intentionally simple —
no JWT, no sessions, no per-user accounts.
"""

from fastapi import Header, HTTPException

from .config import settings


def require_api_key(authorization: str = Header(default="")) -> None:
    """Validate authorization header against the configured dashboard API key.

    FastAPI dependency that checks the Authorization header contains a bearer token
    matching the configured dashboard_api_key. Raises HTTPException with status 401
    if the token is missing or does not match.

    Args:
        authorization: The Authorization header value, passed by FastAPI.

    Raises:
        HTTPException: With status_code 401 if authorization is missing or invalid.
    """
    expected = f"Bearer {settings.dashboard_api_key}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
