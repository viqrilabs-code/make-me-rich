from __future__ import annotations

from sqlalchemy.orm import Session

from app.brokers.base import BrokerAdapter
from app.models import StrategyConfig
from app.services.execution_service import ExecutionService


class MonitoringService:
    def __init__(self, broker: BrokerAdapter) -> None:
        self.execution = ExecutionService(broker)

    def reconcile_open_positions(self, db: Session, strategy: StrategyConfig) -> dict:
        closed_count = self.execution.reconcile_positions(db, strategy)
        performance = self.execution.update_daily_performance(db)
        return {
            "closed_count": closed_count,
            "daily_performance_id": performance.id if performance else None,
        }
