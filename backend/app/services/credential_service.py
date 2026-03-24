from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models import BrokerCredentialMeta


BROKER_CREDENTIAL_NAMES = {"mock", "groww", "indmoney"}


@dataclass(frozen=True, slots=True)
class ApiCredentialDefinition:
    integration: str
    label: str
    settings_field: str
    docs_url: str
    manage_url: str
    description: str
    required_for_trade_fetch: bool
    steps: tuple[str, ...]


API_CREDENTIAL_DEFINITIONS: dict[str, ApiCredentialDefinition] = {
    "indmoney": ApiCredentialDefinition(
        integration="indmoney",
        label="INDstocks access token",
        settings_field="indmoney_api_key",
        docs_url="https://api-docs.indstocks.com/getting-started/",
        manage_url="https://api-docs.indstocks.com/getting-started/#step-2-make-your-first-api-call",
        description="Used for live account, quotes, candles, holdings, and order access through the INDstocks API.",
        required_for_trade_fetch=True,
        steps=(
            "Sign in to the INDstocks developer account linked to your broker access.",
            "Open the Getting Started guide and follow Step 2 to make your first API call.",
            "Copy the access token that the docs show in the Authorization header example.",
            "Paste that token here and save it before fetching trades.",
        ),
    ),
    "openai": ApiCredentialDefinition(
        integration="openai",
        label="ChatGPT / OpenAI API key",
        settings_field="llm_api_key",
        docs_url="https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key",
        manage_url="https://platform.openai.com/api-keys",
        description="Primary provider for the LLM agent and the ReAct agent. If it fails, the app falls back to Claude and then Gemini.",
        required_for_trade_fetch=False,
        steps=(
            "Sign in to the OpenAI Platform with the account that has API billing enabled.",
            "Open the API keys page and create a new secret key.",
            "Copy the key immediately because the full value is only shown once.",
            "Paste it here and save it so the trading assistant can call the model.",
        ),
    ),
    "anthropic": ApiCredentialDefinition(
        integration="anthropic",
        label="Claude / Anthropic API key",
        settings_field="anthropic_api_key",
        docs_url="https://docs.anthropic.com/en/docs/about-claude/models/overview",
        manage_url="https://console.anthropic.com/settings/keys",
        description="First fallback provider after ChatGPT / OpenAI for both the LLM agent and the ReAct agent.",
        required_for_trade_fetch=False,
        steps=(
            "Sign in to the Anthropic Console with the account that has API access enabled.",
            "Open the API keys page in the console settings area.",
            "Create a new API key and copy it while it is visible.",
            "Paste the key here and save it so Claude can be used as the first fallback provider.",
        ),
    ),
    "gemini": ApiCredentialDefinition(
        integration="gemini",
        label="Google Gemini API key",
        settings_field="gemini_api_key",
        docs_url="https://ai.google.dev/gemini-api/docs/openai",
        manage_url="https://aistudio.google.com/apikey",
        description="Final fallback provider after ChatGPT / OpenAI and Claude. Uses Google's OpenAI-compatible Gemini endpoint.",
        required_for_trade_fetch=False,
        steps=(
            "Open Google AI Studio with the Google account that should own the API access.",
            "Create a Gemini API key from the AI Studio API key page.",
            "Use that key for the Gemini OpenAI-compatible endpoint shown in the official docs.",
            "Paste the key here and save it so Gemini can act as the final fallback provider.",
        ),
    ),
    "marketaux": ApiCredentialDefinition(
        integration="marketaux",
        label="Marketaux API key",
        settings_field="marketaux_api_key",
        docs_url="https://www.marketaux.com/",
        manage_url="https://www.marketaux.com/",
        description="Used for live finance headlines and symbol-level news sentiment.",
        required_for_trade_fetch=True,
        steps=(
            "Create or sign in to your Marketaux account.",
            "Generate or copy the API token from the Marketaux dashboard.",
            "Confirm the token works with the api_token query parameter shown in the docs examples.",
            "Paste the key here and save it before running trade analysis.",
        ),
    ),
}


def get_runtime_settings(db: Session | None = None) -> Settings:
    base_settings = get_settings()
    own_session: Session | None = None
    try:
        session = db
        if session is None:
            own_session = SessionLocal()
            session = own_session
        rows = {
            row.broker_name: row
            for row in session.scalars(select(BrokerCredentialMeta)).all()
        }
        overrides: dict[str, str] = {}
        for name, definition in API_CREDENTIAL_DEFINITIONS.items():
            row = rows.get(name)
            secret = _secret_from_row(row)
            if secret:
                overrides[definition.settings_field] = secret
        return base_settings.model_copy(update=overrides)
    except Exception:
        return base_settings
    finally:
        if own_session is not None:
            own_session.close()


def build_api_credential_statuses(db: Session) -> list[dict]:
    settings = get_settings()
    runtime_settings = get_runtime_settings(db)
    rows = {
        row.broker_name: row
        for row in db.scalars(select(BrokerCredentialMeta)).all()
    }

    payload: list[dict] = []
    for name, definition in API_CREDENTIAL_DEFINITIONS.items():
        row = rows.get(name)
        db_secret = _secret_from_row(row)
        effective_secret = getattr(runtime_settings, definition.settings_field, None)
        env_secret = getattr(settings, definition.settings_field, None)
        payload.append(
            {
                "integration": name,
                "label": definition.label,
                "field_name": definition.settings_field,
                "configured": bool(effective_secret),
                "source": (
                    "strategy"
                    if db_secret
                    else "environment"
                    if env_secret
                    else "missing"
                ),
                "masked_value": mask_secret(effective_secret),
                "required_for_trade_fetch": definition.required_for_trade_fetch,
                "description": definition.description,
                "docs_url": definition.docs_url,
                "manage_url": definition.manage_url,
                "steps": list(definition.steps),
            }
        )
    return payload


def save_api_keys(
    db: Session,
    *,
    indmoney_api_key: str | None = None,
    llm_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    gemini_api_key: str | None = None,
    marketaux_api_key: str | None = None,
) -> None:
    rows = {
        row.broker_name: row
        for row in db.scalars(select(BrokerCredentialMeta)).all()
    }
    updates = {
        "indmoney": indmoney_api_key,
        "openai": llm_api_key,
        "anthropic": anthropic_api_key,
        "gemini": gemini_api_key,
        "marketaux": marketaux_api_key,
    }

    for name, raw_value in updates.items():
        clean_value = (raw_value or "").strip()
        if not clean_value:
            continue
        definition = API_CREDENTIAL_DEFINITIONS[name]
        row = rows.get(name)
        if row is None:
            row = BrokerCredentialMeta(
                broker_name=name,
                label=definition.label,
                configured=True,
                secret_source="db",
                metadata_json={},
            )
            db.add(row)
            rows[name] = row

        metadata = dict(row.metadata_json or {})
        metadata["api_key"] = clean_value
        metadata["masked_hint"] = mask_secret(clean_value)
        metadata["updated_from_strategy_at"] = datetime.now(timezone.utc).isoformat()
        row.label = definition.label
        row.configured = True
        row.secret_source = "db"
        row.metadata_json = metadata


def missing_trade_credentials(db: Session, selected_broker: str) -> list[str]:
    del selected_broker
    settings = get_runtime_settings(db)
    missing: list[str] = []

    if not settings.indmoney_api_key:
        missing.append("Add your INDstocks access token in Strategy -> API keys.")
    if not any([settings.llm_api_key, settings.anthropic_api_key, settings.gemini_api_key]):
        missing.append("Add at least one AI provider key in Strategy -> API keys (ChatGPT, Claude, or Gemini).")
    if not settings.marketaux_api_key:
        missing.append("Add your Marketaux API key in Strategy -> API keys.")

    return missing


def is_trade_fetch_ready(db: Session, selected_broker: str) -> bool:
    return not missing_trade_credentials(db, selected_broker)


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    clean = value.strip()
    if len(clean) <= 8:
        return "*" * len(clean)
    return f"{clean[:4]}...{clean[-4:]}"


def _secret_from_row(row: BrokerCredentialMeta | None) -> str | None:
    if not row:
        return None
    value = str((row.metadata_json or {}).get("api_key") or "").strip()
    return value or None
