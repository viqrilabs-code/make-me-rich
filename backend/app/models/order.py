from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), index=True)
    client_order_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    instrument_type: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(16))
    order_type: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    trigger_price: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), index=True)
    fill_price: Mapped[float | None] = mapped_column(Float)
    fill_quantity: Mapped[float | None] = mapped_column(Float)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="advisory")
    raw_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)

