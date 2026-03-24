from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import DailyPerformance, StrategyConfig, TradingGoal
from app.models.base import Base


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        session.add(
            StrategyConfig(
                polling_interval_minutes=5,
                mode="paper",
                risk_profile="balanced",
                allowed_instruments_json={"instrument_types": ["STOCK"], "symbols": ["INFY"]},
                watchlist_symbols_json=["INFY"],
                max_risk_per_trade_pct=1.0,
                max_daily_loss_pct=2.0,
                max_drawdown_pct=8.0,
                max_open_positions=2,
                max_capital_per_trade_pct=20.0,
                leverage_enabled=False,
                futures_enabled=False,
                options_enabled=False,
                shorting_enabled=False,
                market_hours_only=False,
                kill_switch=False,
                mandatory_stop_loss=True,
                cooldown_after_losses=2,
                cooldown_minutes=60,
                selected_broker="mock",
                live_mode_armed=False,
                pause_scheduler=False,
            )
        )
        session.add(
            TradingGoal(
                initial_capital=100000.0,
                target_multiplier=1.2,
                target_amount=120000.0,
                start_date=date.today(),
                target_date=date.today().fromordinal(date.today().toordinal() + 60),
                status="active",
            )
        )
        session.add(
            DailyPerformance(
                trading_date=date.today(),
                opening_equity=100000.0,
                closing_equity=100000.0,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                drawdown_pct=0.0,
                trades_count=0,
            )
        )
        session.commit()
        yield session


@pytest.fixture()
def strategy(db_session: Session) -> StrategyConfig:
    return db_session.query(StrategyConfig).first()


@pytest.fixture()
def goal(db_session: Session) -> TradingGoal:
    return db_session.query(TradingGoal).first()

