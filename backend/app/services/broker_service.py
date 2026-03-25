from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brokers import MockBrokerAdapter, get_broker_adapter
from app.brokers.base import BrokerAdapter
from app.brokers.types import BrokerHealth
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import BrokerCredentialMeta, StrategyConfig


logger = logging.getLogger(__name__)


def get_strategy_config(db: Session) -> StrategyConfig:
    return db.scalar(select(StrategyConfig).limit(1))


def get_active_broker(db: Session) -> tuple[BrokerAdapter, str, bool]:
    strategy = get_strategy_config(db)
    selected = strategy.selected_broker if strategy else "mock"
    adapter = get_broker_adapter(selected, SessionLocal)
    health = adapter.healthcheck()
    if selected != "mock" and not health.healthy:
        logger.warning("Broker unhealthy, falling back to mock", extra={"selected": selected})
        return MockBrokerAdapter(SessionLocal), "mock", True
    return adapter, selected, False


def get_broker_health(db: Session) -> BrokerHealth:
    strategy = get_strategy_config(db)
    selected = strategy.selected_broker if strategy else "mock"
    selected_adapter = get_broker_adapter(selected, SessionLocal)
    selected_health = selected_adapter.healthcheck()
    using_fallback = selected != "mock" and not selected_health.healthy
    active_broker = "mock" if using_fallback else selected
    selected_health.details.update(
        {
            "selected_broker": selected,
            "active_broker": active_broker,
            "using_fallback": using_fallback,
        }
    )
    return selected_health


def test_broker_connection(db: Session, broker_name: str | None = None) -> BrokerHealth:
    strategy = get_strategy_config(db)
    requested = (broker_name or (strategy.selected_broker if strategy else "mock")).lower()
    adapter = get_broker_adapter(requested, SessionLocal)
    health = adapter.healthcheck()

    meta = db.scalar(
        select(BrokerCredentialMeta).where(BrokerCredentialMeta.broker_name == requested)
    )
    if meta:
        meta.configured = health.healthy or requested == "mock"
        meta.last_validated_at = datetime.now(timezone.utc)
        merged = dict(meta.metadata_json or {})
        merged["last_healthcheck"] = health.model_dump()
        meta.metadata_json = merged
        db.commit()

    return health
