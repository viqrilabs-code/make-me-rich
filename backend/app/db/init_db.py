from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import engine
from app.models import AuditLog, BrokerCredentialMeta, StrategyConfig, TradingGoal, UserConfig
from app.models.base import Base
from app.services.credential_service import API_CREDENTIAL_DEFINITIONS


logger = logging.getLogger(__name__)


def _preferred_broker_name() -> str:
    settings = get_settings()
    if settings.groww_api_key:
        return "groww"
    if settings.indmoney_api_key:
        return "indmoney"
    return "mock"


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def seed_defaults(db: Session) -> None:
    settings = get_settings()
    preferred_broker = _preferred_broker_name()
    user = db.scalar(select(UserConfig).limit(1))
    if not user and settings.bootstrap_admin_on_startup:
        db.add(
            UserConfig(
                admin_username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                timezone=settings.timezone,
            )
        )

    goal = db.scalar(select(TradingGoal).limit(1))
    if not goal:
        start_date = date.today()
        db.add(
            TradingGoal(
                initial_capital=100000.0,
                target_multiplier=1.2,
                target_amount=120000.0,
                start_date=start_date,
                target_date=start_date + timedelta(days=90),
                status="active",
            )
        )

    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        db.add(
            StrategyConfig(
                polling_interval_minutes=settings.scheduler_poll_fallback_minutes,
                mode="advisory",
                risk_profile="balanced",
                allowed_instruments_json={
                    "instrument_types": ["STOCK"],
                    "symbols": settings.default_watchlist_symbols,
                },
                watchlist_symbols_json=settings.default_watchlist_symbols,
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
                selected_broker=preferred_broker,
                preferred_llm_provider="openai",
                live_mode_armed=False,
                pause_scheduler=False,
            )
        )
    elif preferred_broker == "groww" and strategy.selected_broker in {"mock", "indmoney"}:
        strategy.selected_broker = "groww"
    elif strategy.selected_broker == "mock" and preferred_broker != "mock":
        strategy.selected_broker = preferred_broker

    configured_flags = {
        "mock": True,
        "groww": bool(settings.groww_api_key),
        "indmoney": bool(settings.indmoney_api_key),
        "openai": bool(settings.llm_api_key),
        "anthropic": bool(settings.anthropic_api_key),
        "gemini": bool(settings.gemini_api_key),
        "marketaux": bool(settings.marketaux_api_key),
    }
    labels = {
        "mock": "Mock Broker",
        "groww": "Groww",
        "indmoney": "INDstocks (Legacy)",
        "openai": API_CREDENTIAL_DEFINITIONS["openai"].label,
        "anthropic": API_CREDENTIAL_DEFINITIONS["anthropic"].label,
        "gemini": API_CREDENTIAL_DEFINITIONS["gemini"].label,
        "marketaux": API_CREDENTIAL_DEFINITIONS["marketaux"].label,
    }
    existing_brokers = {
        row.broker_name: row for row in db.scalars(select(BrokerCredentialMeta)).all()
    }
    for broker_name in {"mock", "groww", "indmoney", "openai", "anthropic", "gemini", "marketaux"}:
        meta = existing_brokers.get(broker_name)
        db_configured = bool((meta.metadata_json or {}).get("api_key")) if meta else False
        if not meta:
            db.add(
                BrokerCredentialMeta(
                    broker_name=broker_name,
                    label=labels[broker_name],
                    configured=configured_flags[broker_name],
                    secret_source="env",
                    metadata_json={},
                )
            )
            continue

        meta.label = labels[broker_name]
        meta.configured = configured_flags[broker_name] or db_configured
        if db_configured and meta.secret_source == "env":
            meta.secret_source = "db"

    if not db.scalar(select(AuditLog).limit(1)):
        db.add(
            AuditLog(
                category="system",
                message="Database initialized with default single-user configuration.",
                metadata_json={
                    "seeded_at": datetime.now(timezone.utc).isoformat(),
                    "bootstrap_admin_on_startup": settings.bootstrap_admin_on_startup,
                },
            )
        )

    db.commit()
    logger.info("Database defaults ensured")
