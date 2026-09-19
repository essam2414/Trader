"""FastAPI application entrypoint. Defines the `app` instance and top-level routes;
later tasks mount portfolio routers and wire up the DB/scheduler here."""

from fastapi import FastAPI

app = FastAPI(title="Trader API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check used by deployment platforms/monitoring to confirm the API is up."""
    return {"status": "ok"}
