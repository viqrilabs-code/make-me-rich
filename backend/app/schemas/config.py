from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.goal import GoalResponse
from app.schemas.strategy import StrategyResponse


class BrokerCredentialMetaResponse(ORMModel):
    id: int
    broker_name: str
    label: str
    configured: bool
    last_validated_at: datetime | None = None
    secret_source: str
    metadata_json: dict


class ApiCredentialResponse(BaseModel):
    integration: str
    label: str
    field_name: str
    configured: bool
    source: str
    masked_value: str | None = None
    required_for_trade_fetch: bool
    description: str
    docs_url: str
    manage_url: str
    steps: list[str]


class ConfigResponse(BaseModel):
    user: dict
    goal: GoalResponse | None
    strategy: StrategyResponse | None
    broker_credentials: list[BrokerCredentialMetaResponse]
    api_credentials: list[ApiCredentialResponse]
    secret_status: dict


class ConfigUpdate(BaseModel):
    timezone: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)
    selected_broker: str | None = None
    broker_metadata: dict[str, dict] | None = None
    indmoney_api_key: str | None = Field(default=None, max_length=4096)
    llm_api_key: str | None = Field(default=None, max_length=4096)
    anthropic_api_key: str | None = Field(default=None, max_length=4096)
    gemini_api_key: str | None = Field(default=None, max_length=4096)
    marketaux_api_key: str | None = Field(default=None, max_length=4096)
