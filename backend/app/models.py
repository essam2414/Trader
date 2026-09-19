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
