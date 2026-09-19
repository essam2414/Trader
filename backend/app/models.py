"""SQLAlchemy ORM models for the Trading212 portfolio dashboard backend."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PortfolioSnapshot(Base):
    """A point-in-time snapshot of portfolio value.

    Taken periodically by the scheduler (added in a later task) and used to
    build the equity-curve chart on the dashboard.
    """

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    total_value: Mapped[float] = mapped_column(Float)
    unrealized_profit_loss: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))


class OrderFill(Base):
    """A single executed buy/sell fill, synced from Trading212's order history.

    Only fills of type "TRADE" are stored — corporate-action fills (stock
    splits, stock dividends, spin-offs, etc.) are filtered out during sync
    since they'd corrupt FIFO trade reconstruction if included.
    """

    __tablename__ = "order_fills"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(String)
    ticker: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[float] = mapped_column(Float)
    fill_price: Mapped[float] = mapped_column(Float)
    net_value: Mapped[float] = mapped_column(Float)
    realised_profit_loss: Mapped[float] = mapped_column(Float, default=0.0)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Dividend(Base):
    """A single dividend payment, synced from Trading212's dividend history."""

    __tablename__ = "dividends"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    type: Mapped[str] = mapped_column(String)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
