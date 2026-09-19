"""Portfolio API routes.

Exposes the current live portfolio (account summary + positions, fetched
live from Trading212) and the historical equity-curve data (stored
PortfolioSnapshot rows). All routes require the shared dashboard API key.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..dependencies import get_db, get_trading212_client
from ..models import PortfolioSnapshot
from ..schemas import AccountSummary, CashBreakdown, PortfolioCurrent, PortfolioSnapshotOut, Position
from ..trading212 import Trading212Client

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/portfolio/current", response_model=PortfolioCurrent)
def get_current_portfolio(client: Trading212Client = Depends(get_trading212_client)) -> PortfolioCurrent:
    """Fetch the live account summary and open positions from Trading212.

    Translates any Trading212 connection/auth failure into a 502 so the frontend
    can show a clear "Trading212 isn't connected" message instead of an opaque 500.
    """
    try:
        summary = client.get_account_summary()
        positions = client.get_positions()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to Trading212 - check your API credentials.",
        ) from exc
    return PortfolioCurrent(
        account=AccountSummary(
            id=summary["id"],
            currency=summary["currency"],
            totalValue=summary["totalValue"],
            cash=CashBreakdown(**summary["cash"]),
            unrealizedProfitLoss=summary["investments"]["unrealizedProfitLoss"],
            realizedProfitLoss=summary["investments"]["realizedProfitLoss"],
        ),
        positions=[
            Position(
                ticker=p["instrument"]["ticker"],
                name=p["instrument"]["name"],
                currency=p["instrument"]["currency"],
                quantity=p["quantity"],
                averagePricePaid=p["averagePricePaid"],
                currentPrice=p["currentPrice"],
                currentValue=p["walletImpact"]["currentValue"],
                unrealizedProfitLoss=p["walletImpact"]["unrealizedProfitLoss"],
            )
            for p in positions
        ],
    )


@router.get("/portfolio/history", response_model=list[PortfolioSnapshotOut])
def get_portfolio_history(db: Session = Depends(get_db)) -> list[PortfolioSnapshotOut]:
    """Return all stored portfolio snapshots, oldest first, for the equity-curve chart."""
    rows = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.taken_at).all()
    return [
        PortfolioSnapshotOut(
            takenAt=row.taken_at,
            totalValue=row.total_value,
            unrealizedProfitLoss=row.unrealized_profit_loss,
        )
        for row in rows
    ]
