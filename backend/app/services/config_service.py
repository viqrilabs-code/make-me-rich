from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import BrokerCredentialMeta, StrategyConfig, TradingGoal, UserConfig
from app.schemas.config import ApiCredentialResponse, BrokerCredentialMetaResponse, ConfigResponse, ConfigUpdate
from app.schemas.goal import GoalPlanResponse, GoalResponse
from app.schemas.strategy import StrategyResponse
from app.services.credential_service import (
    BROKER_CREDENTIAL_NAMES,
    build_api_credential_statuses,
    get_runtime_settings,
    save_api_keys,
)
from app.services.goal_planner import compute_goal_plan


def get_config_bundle(db: Session) -> ConfigResponse:
    settings = get_settings()
    runtime_settings = get_runtime_settings(db)
    user = db.scalar(select(UserConfig).limit(1))
    goal = db.scalar(select(TradingGoal).order_by(TradingGoal.updated_at.desc()).limit(1))
    strategy = db.scalar(select(StrategyConfig).order_by(StrategyConfig.updated_at.desc()).limit(1))
    credentials = db.scalars(select(BrokerCredentialMeta).order_by(BrokerCredentialMeta.broker_name)).all()

    goal_payload = None
    if goal:
        plan = compute_goal_plan(goal, current_capital=goal.initial_capital)
        goal_payload = GoalResponse(
            **GoalResponse.model_validate(goal).model_dump(exclude={"plan"}),
            plan=GoalPlanResponse(**asdict(plan)),
        )

    return ConfigResponse(
        user={
            "id": user.id if user else 0,
            "admin_username": user.admin_username if user else settings.admin_username,
            "timezone": user.timezone if user else settings.timezone,
        },
        goal=goal_payload,
        strategy=StrategyResponse.model_validate(strategy) if strategy else None,
        broker_credentials=[
            BrokerCredentialMetaResponse.model_validate(
                {
                    **BrokerCredentialMetaResponse.model_validate(credential).model_dump(),
                    "metadata_json": _sanitize_metadata(credential.metadata_json),
                }
            )
            for credential in credentials
            if credential.broker_name in BROKER_CREDENTIAL_NAMES
        ],
        api_credentials=[
            ApiCredentialResponse.model_validate(item)
            for item in build_api_credential_statuses(db)
        ],
        secret_status={
            "marketaux_configured": bool(runtime_settings.marketaux_api_key),
            "llm_configured": bool(runtime_settings.llm_api_key),
            "anthropic_configured": bool(runtime_settings.anthropic_api_key),
            "gemini_configured": bool(runtime_settings.gemini_api_key),
            "llm_fallback_configured": bool(runtime_settings.anthropic_api_key or runtime_settings.gemini_api_key),
            "groww_configured": bool(runtime_settings.groww_client_id and runtime_settings.groww_api_key),
            "indmoney_configured": bool(runtime_settings.indmoney_api_key),
            "live_execution_enabled": settings.live_execution_enabled,
        },
    )


def update_config_bundle(db: Session, payload: ConfigUpdate) -> ConfigResponse:
    user = db.scalar(select(UserConfig).limit(1))
    strategy = db.scalar(select(StrategyConfig).limit(1))
    credentials = {
        item.broker_name: item
        for item in db.scalars(select(BrokerCredentialMeta)).all()
    }

    if user and payload.timezone:
        user.timezone = payload.timezone
    if user and payload.new_password:
        user.password_hash = hash_password(payload.new_password)
    if strategy and payload.selected_broker:
        strategy.selected_broker = payload.selected_broker.lower()

    if payload.broker_metadata:
        for broker_name, metadata in payload.broker_metadata.items():
            if broker_name in credentials:
                credentials[broker_name].metadata_json = metadata

    save_api_keys(
        db,
        indmoney_api_key=payload.indmoney_api_key,
        llm_api_key=payload.llm_api_key,
        anthropic_api_key=payload.anthropic_api_key,
        gemini_api_key=payload.gemini_api_key,
        marketaux_api_key=payload.marketaux_api_key,
    )

    db.commit()
    return get_config_bundle(db)


def _sanitize_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}
    cleaned = dict(metadata)
    if "api_key" in cleaned:
        cleaned["api_key"] = "***"
    return cleaned
