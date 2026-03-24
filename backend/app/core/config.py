from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Viqri Trading Assistant"
    app_env: str = "development"
    api_prefix: str = "/api"
    secret_key: str = Field(default="change-me-in-production", min_length=16)
    timezone: str = "Asia/Kolkata"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    sqlite_path: str = "./backend/data/trading.db"
    admin_username: str = "admin"
    admin_password: str = "change-this-password"
    bootstrap_admin_on_startup: bool = False
    session_cookie_name: str = "trading_session"
    session_ttl_hours: int = 12
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300
    marketaux_api_key: str | None = None
    marketaux_base_url: str = "https://api.marketaux.com/v1/news/all"
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-5-mini"
    anthropic_api_base: str = "https://api.anthropic.com/v1"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash-preview"
    llm_timeout_seconds: int = 20
    llm_temperature: float = 0.1
    default_watchlist: str = "RELIANCE,TCS,INFY,HDFCBANK,NIFTYBEES"
    scheduler_poll_fallback_minutes: int = 5
    scheduler_monitor_minutes: int = 2
    scheduler_eod_hour_ist: int = 16
    scheduler_eod_minute_ist: int = 0
    market_stale_after_minutes: int = 15
    paper_trading_slippage_pct: float = 0.001
    paper_trading_fee_pct: float = 0.0005
    live_execution_enabled: bool = False
    groww_base_url: str = "https://api.groww.in"
    groww_client_id: str | None = None
    groww_api_key: str | None = None
    groww_api_secret: str | None = None
    indmoney_base_url: str = "https://api.indstocks.com"
    indmoney_client_id: str | None = None
    indmoney_api_key: str | None = None
    indmoney_api_secret: str | None = None

    @field_validator("sqlite_path")
    @classmethod
    def normalize_sqlite_path(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            path = (BASE_DIR / value).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    @field_validator("default_watchlist")
    @classmethod
    def normalize_watchlist(cls, value: str) -> str:
        items = [item.strip().upper() for item in value.split(",") if item.strip()]
        return ",".join(items)

    @computed_field
    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path}"

    @computed_field
    @property
    def default_watchlist_symbols(self) -> list[str]:
        return [item for item in self.default_watchlist.split(",") if item]

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        return [self.frontend_origin]

    def public_status(self) -> dict[str, Any]:
        return {
            "marketaux_configured": bool(self.marketaux_api_key),
            "llm_configured": bool(self.llm_api_key),
            "anthropic_configured": bool(self.anthropic_api_key),
            "gemini_configured": bool(self.gemini_api_key),
            "llm_fallback_configured": bool(self.anthropic_api_key or self.gemini_api_key),
            "groww_configured": bool(self.groww_client_id and self.groww_api_key),
            "indmoney_configured": bool(self.indmoney_api_key),
            "live_execution_enabled": self.live_execution_enabled,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
