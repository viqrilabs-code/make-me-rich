from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.brokers.types import BrokerAccount
from app.core.config import get_settings
from app.db.init_db import seed_defaults
from app.models import BrokerCredentialMeta, StrategyConfig
from app.models.base import Base
from app.models import SchedulerRun, UserConfig
from app.services import dashboard_service
from app.services.config_service import get_config_bundle
from app.services.orchestration_service import should_run_poll


def test_get_config_bundle_serializes_goal_plan(db_session) -> None:
    bundle = get_config_bundle(db_session)
    assert bundle.goal is not None
    assert bundle.goal.plan is not None
    assert bundle.goal.plan.target_amount > 0


def test_should_run_poll_handles_naive_sqlite_timestamp(db_session) -> None:
    db_session.add(
        SchedulerRun(
            started_at=datetime.now(),
            completed_at=None,
            status="completed",
            lock_acquired=True,
            actions_taken_json=[],
            error_message=None,
        )
    )
    db_session.commit()

    should_run, next_due = should_run_poll(db_session)

    assert isinstance(should_run, bool)
    assert next_due is not None
    assert next_due.tzinfo is not None


def test_seed_defaults_prefers_indmoney_when_token_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.db.init_db.get_settings",
        lambda: get_settings().model_copy(
            update={
                "groww_api_key": None,
                "groww_api_secret": None,
                "indmoney_api_key": "demo-token",
            }
        ),
    )

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        seed_defaults(session)
        strategy = session.scalar(select(StrategyConfig).limit(1))
        broker_meta = session.scalar(
            select(BrokerCredentialMeta).where(BrokerCredentialMeta.broker_name == "indmoney")
        )

        assert strategy is not None
        assert strategy.selected_broker == "indmoney"
        assert broker_meta is not None
        assert broker_meta.configured is True

def test_seed_defaults_prefers_groww_when_api_key_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.db.init_db.get_settings",
        lambda: get_settings().model_copy(
            update={
                "groww_api_key": "groww-demo-token",
                "groww_api_secret": None,
                "indmoney_api_key": None,
            }
        ),
    )

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        seed_defaults(session)
        strategy = session.scalar(select(StrategyConfig).limit(1))
        broker_meta = session.scalar(
            select(BrokerCredentialMeta).where(BrokerCredentialMeta.broker_name == "groww")
        )

        assert strategy is not None
        assert strategy.selected_broker == "groww"
        assert broker_meta is not None
        assert broker_meta.configured is True

def test_seed_defaults_upgrades_existing_indmoney_selection_to_groww_when_groww_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.db.init_db.get_settings",
        lambda: get_settings().model_copy(
            update={
                "groww_api_key": "groww-demo-token",
                "groww_api_secret": None,
                "indmoney_api_key": None,
            }
        ),
    )

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            StrategyConfig(
                polling_interval_minutes=5,
                mode="advisory",
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
                market_hours_only=True,
                kill_switch=False,
                mandatory_stop_loss=True,
                cooldown_after_losses=2,
                cooldown_minutes=60,
                selected_broker="indmoney",
                preferred_llm_provider="openai",
                live_mode_armed=False,
                pause_scheduler=False,
            )
        )
        session.commit()

        seed_defaults(session)
        strategy = session.scalar(select(StrategyConfig).limit(1))

        assert strategy is not None
        assert strategy.selected_broker == "groww"


def test_seed_defaults_does_not_create_user_without_bootstrap_flag(monkeypatch) -> None:
    monkeypatch.delenv("BOOTSTRAP_ADMIN_ON_STARTUP", raising=False)
    get_settings.cache_clear()

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        seed_defaults(session)
        user = session.scalar(select(UserConfig).limit(1))
        strategy = session.scalar(select(StrategyConfig).limit(1))

        assert user is None
        assert strategy is not None

    get_settings.cache_clear()


def test_refresh_live_portfolio_cache_reuses_recent_broker_state(db_session, strategy, monkeypatch) -> None:
    strategy.selected_broker = "groww"
    db_session.commit()

    calls = {"account": 0, "positions": 0, "holdings": 0}

    class CountingAdapter:
        def get_account(self):
            calls["account"] += 1
            return BrokerAccount(
                cash_balance=100000.0,
                total_equity=101500.0,
                margin_available=75000.0,
                realized_pnl=250.0,
                unrealized_pnl=1250.0,
                source="groww",
                raw_payload={},
            )

        def get_positions(self):
            calls["positions"] += 1
            return []

        def get_holdings(self):
            calls["holdings"] += 1
            return []

    monkeypatch.setattr(dashboard_service, "_BROKER_PORTFOLIO_CACHE", None)
    monkeypatch.setattr(
        dashboard_service,
        "get_active_broker",
        lambda db: (CountingAdapter(), "groww", False),
    )

    first = dashboard_service.refresh_live_portfolio_cache(db_session)
    second = dashboard_service.refresh_live_portfolio_cache(db_session)

    assert first[2] is not None
    assert second[2] is not None
    assert calls == {"account": 1, "positions": 1, "holdings": 1}
