from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TradingGoal(TimestampMixin, Base):
    __tablename__ = "trading_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    initial_capital: Mapped[float] = mapped_column(Float)
    target_multiplier: Mapped[float] = mapped_column(Float)
    target_amount: Mapped[float] = mapped_column(Float)
    start_date: Mapped[date] = mapped_column(Date)
    target_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="active")

