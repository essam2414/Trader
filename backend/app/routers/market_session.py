"""Read-only US equity market-session status for the dashboard."""

from fastapi import APIRouter, Depends, HTTPException

from ..alpaca_market_data import AlpacaMarketDataClient, AlpacaUnavailableError
from ..auth import require_api_key
from ..dependencies import get_alpaca_market_data_client
from ..schemas import MarketSessionOut

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/market-session", response_model=MarketSessionOut)
def get_market_session(
    client: AlpacaMarketDataClient | None = Depends(get_alpaca_market_data_client),
) -> MarketSessionOut:
    """Report the exchange schedule, including holidays and early closes."""
    if client is None:
        raise HTTPException(status_code=503, detail="Alpaca market data is not configured")
    try:
        status = client.get_market_session()
    except AlpacaUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Market schedule is temporarily unavailable") from exc
    return MarketSessionOut(
        phase=status.phase,
        asOf=status.as_of,
        endsAt=status.ends_at,
        nextPhase=status.next_phase,
        nextPhaseStartsAt=status.next_phase_starts_at,
        isEarlyClose=status.is_early_close,
    )
