from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.brokers.base import BrokerAdapter
from app.brokers.groww import GrowwAdapter
from app.brokers.indmoney import INDMoneyAdapter
from app.brokers.mock import MockBrokerAdapter
from app.services.credential_service import get_runtime_settings


def get_broker_adapter(name: str, db_factory: sessionmaker[Session]) -> BrokerAdapter:
    settings = get_runtime_settings()
    normalized = (name or "mock").lower()
    if normalized == "groww":
        return GrowwAdapter(settings)
    if normalized == "indmoney":
        return INDMoneyAdapter(settings)
    return MockBrokerAdapter(db_factory)
