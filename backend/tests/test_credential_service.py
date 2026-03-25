from __future__ import annotations

from types import SimpleNamespace

from app.core.config import get_settings
from app.models import BrokerCredentialMeta
from app.services.credential_service import get_runtime_settings, missing_trade_credentials


def test_runtime_settings_prefer_strategy_saved_api_keys(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.credential_service.get_settings",
        lambda: get_settings().model_copy(
            update={
                "groww_api_key": None,
                "groww_api_secret": None,
                "indmoney_api_key": None,
                "llm_api_key": None,
                "anthropic_api_key": None,
                "gemini_api_key": None,
                "marketaux_api_key": None,
            }
        ),
    )
    db_session.add(
        BrokerCredentialMeta(
            broker_name="groww",
            label="Groww API key or access token",
            configured=True,
            secret_source="db",
            metadata_json={"api_key": "groww-test-key", "api_secret": "groww-test-secret"},
        )
    )
    db_session.add(
        BrokerCredentialMeta(
            broker_name="openai",
            label="ChatGPT / OpenAI API key",
            configured=True,
            secret_source="db",
            metadata_json={"api_key": "sk-test-openai"},
        )
    )
    db_session.add(
        BrokerCredentialMeta(
            broker_name="marketaux",
            label="Marketaux API key",
            configured=True,
            secret_source="db",
            metadata_json={"api_key": "marketaux-test-key"},
        )
    )
    db_session.commit()

    settings = get_runtime_settings(db_session)

    assert settings.groww_api_key == "groww-test-key"
    assert settings.groww_api_secret == "groww-test-secret"
    assert settings.llm_api_key == "sk-test-openai"
    assert settings.marketaux_api_key == "marketaux-test-key"


def test_missing_trade_credentials_points_user_back_to_strategy(monkeypatch, db_session) -> None:
    monkeypatch.setattr(
        "app.services.credential_service.get_runtime_settings",
        lambda db=None: SimpleNamespace(  # noqa: ARG005
            groww_api_key=None,
            llm_api_key=None,
            anthropic_api_key=None,
            gemini_api_key=None,
            marketaux_api_key=None,
        ),
    )

    missing = missing_trade_credentials(db_session, "groww")

    assert len(missing) == 2
    assert all("Strategy -> API keys" in message for message in missing)
