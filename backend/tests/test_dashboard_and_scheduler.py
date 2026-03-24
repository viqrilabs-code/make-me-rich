from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.init_db import seed_defaults
from app.models import BrokerCredentialMeta, StrategyConfig
from app.models.base import Base
from app.models import SchedulerRun, UserConfig
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
    monkeypatch.setenv("INDMONEY_API_KEY", "demo-token")
    get_settings.cache_clear()

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

    get_settings.cache_clear()


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
