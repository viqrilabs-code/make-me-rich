from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyPerformance(Base):
    __tablename__ = "daily_performance"

    id: Mapped[int] = mapped_column(primary_key=True)
    trading_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    opening_equity: Mapped[float] = mapped_column(Float)
    closing_equity: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    trades_count: Mapped[int] = mapped_column(Integer, default=0)

