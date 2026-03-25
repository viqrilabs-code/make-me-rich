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
    "groww": ApiCredentialDefinition(
        integration="groww",
        label="Groww API key or access token",
        settings_field="groww_api_key",
        docs_url="https://groww.in/trade-api/docs/python-sdk",
        manage_url="https://groww.in/trade-api",
        description="Primary live broker credential for Groww. Paste the API key here, or paste a ready access token if you already generated one outside the app.",
        required_for_trade_fetch=True,
        steps=(
            "Open Groww Trade API and sign in with the Groww account that has the trading API subscription enabled.",
            "Go to the API keys page and choose Generate API key.",
            "Copy the API key and paste it here, or paste a current access token if you already generated one with the SDK flow.",
            "If you are using the daily API key + secret flow, paste the matching secret in the Groww API secret field below and save both fields.",
        ),
    ),
    "groww_secret": ApiCredentialDefinition(
        integration="groww_secret",
        label="Groww API secret",
        settings_field="groww_api_secret",
        docs_url="https://groww.in/trade-api/docs/python-sdk",
        manage_url="https://groww.in/trade-api",
        description="Optional companion secret for the official Groww API key flow. Leave blank only if you are pasting a ready Groww access token in the main Groww field.",
        required_for_trade_fetch=False,
        steps=(
            "Open the Groww API keys page from the Groww Trade API dashboard.",
            "Generate an API key if you have not already done so.",
            "Copy the API secret that is shown with the key pair.",
            "Paste it here so the app can generate a fresh access token through the official Groww SDK flow.",
        ),
    ),
    "indmoney": ApiCredentialDefinition(
        integration="indmoney",
        label="INDstocks access token (legacy)",
        settings_field="indmoney_api_key",
        docs_url="https://api-docs.indstocks.com/getting-started/",
        manage_url="https://api-docs.indstocks.com/getting-started/#step-2-make-your-first-api-call",
        description="Legacy live broker path through the INDstocks API. Keep this only if you still want to use the older broker integration.",
        required_for_trade_fetch=False,
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
        description="Optional live finance headline feed. If it is missing, the app switches to technical-only trade analysis instead of blocking search.",
        required_for_trade_fetch=False,
        steps=(
            "Create or sign in to your Marketaux account.",
            "Generate or copy the API token from the Marketaux dashboard.",
            "Confirm the token works with the api_token query parameter shown in the docs examples.",
            "Paste the key here and save it if you want live news to supplement the chart-based analysis.",
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
            row = rows.get(_credential_row_name(name))
            secret = _secret_from_row(row, _metadata_key_for_integration(name))
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
        row = rows.get(_credential_row_name(name))
        db_secret = _secret_from_row(row, _metadata_key_for_integration(name))
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
    groww_api_key: str | None = None,
    groww_api_secret: str | None = None,
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
        "groww": {
            "api_key": groww_api_key,
            "api_secret": groww_api_secret,
        },
        "indmoney": {"api_key": indmoney_api_key},
        "openai": {"api_key": llm_api_key},
        "anthropic": {"api_key": anthropic_api_key},
        "gemini": {"api_key": gemini_api_key},
        "marketaux": {"api_key": marketaux_api_key},
    }

    for name, fields in updates.items():
        clean_fields = {field_name: (raw_value or "").strip() for field_name, raw_value in fields.items() if (raw_value or "").strip()}
        if not clean_fields:
            continue
        definition = API_CREDENTIAL_DEFINITIONS["groww"] if name == "groww" else API_CREDENTIAL_DEFINITIONS[name]
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
        for field_name, clean_value in clean_fields.items():
            metadata[field_name] = clean_value
            metadata[f"{field_name}_masked_hint"] = mask_secret(clean_value)
        metadata["updated_from_strategy_at"] = datetime.now(timezone.utc).isoformat()
        row.label = definition.label
        row.configured = True
        row.secret_source = "db"
        row.metadata_json = metadata


def missing_trade_credentials(db: Session, selected_broker: str) -> list[str]:
    settings = get_runtime_settings(db)
    missing: list[str] = []

    broker = (selected_broker or "mock").lower()
    if broker == "groww" and not settings.groww_api_key:
        missing.append("Add your Groww API key or access token in Strategy -> API keys.")
    if broker == "indmoney" and not settings.indmoney_api_key:
        missing.append("Add your INDstocks access token in Strategy -> API keys.")
    if not any([settings.llm_api_key, settings.anthropic_api_key, settings.gemini_api_key]):
        missing.append("Add at least one AI provider key in Strategy -> API keys (ChatGPT, Claude, or Gemini).")

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


def _credential_row_name(integration: str) -> str:
    if integration in {"groww", "groww_secret"}:
        return "groww"
    return integration


def _metadata_key_for_integration(integration: str) -> str:
    if integration == "groww_secret":
        return "api_secret"
    return "api_key"


def _secret_from_row(row: BrokerCredentialMeta | None, key: str = "api_key") -> str | None:
    if not row:
        return None
    value = str((row.metadata_json or {}).get(key) or "").strip()
    return value or None
