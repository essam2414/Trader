"""Tests for the /health liveness endpoint."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    """The /health endpoint should return a 200 status with a simple ok payload."""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
