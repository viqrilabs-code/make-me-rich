from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BrokerCredentialMeta(TimestampMixin, Base):
    __tablename__ = "broker_credential_meta"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker_name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(64))
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    secret_source: Mapped[str] = mapped_column(String(32), default="env")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

