import json
from unittest.mock import Mock

import httpx

from app.llm.service import LLMDecisionEngine


def test_llm_invalid_response_falls_back_to_hold(db_session, monkeypatch) -> None:
    engine = LLMDecisionEngine()
    engine.settings.llm_api_key = "test-key"
    monkeypatch.setattr("app.llm.service.get_runtime_settings", lambda db=None: engine.settings)

    def fake_post(*args, **kwargs):  # noqa: ANN002,ANN003
        response = Mock()
        response.raise_for_status = Mock()
        response.json = Mock(return_value={"choices": [{"message": {"content": "not-json"}}]})
        return response

    original_post = httpx.post
    httpx.post = fake_post
    try:
        decision = engine.request_decision(
            {
                "default_symbol": "INFY",
                "candidate_actions": [{"symbol": "INFY", "action": "BUY_STOCK", "instrument_type": "STOCK", "side": "BUY", "score": 0.8}],
                "quotes": {"INFY": {"ltp": 1500.0}},
            },
            db_session,
        )
    finally:
        httpx.post = original_post

    assert decision.action == "HOLD"


def test_llm_quota_error_surfaces_precise_reason(db_session, monkeypatch) -> None:
    engine = LLMDecisionEngine()
    engine.settings.llm_api_key = "test-key"
    engine.settings.anthropic_api_key = None
    engine.settings.gemini_api_key = None
    monkeypatch.setattr("app.llm.service.get_runtime_settings", lambda db=None: engine.settings)

    def fake_post(*args, **kwargs):  # noqa: ANN002,ANN003
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return httpx.Response(
            429,
            request=request,
            json={
                "error": {
                    "message": "You exceeded your current quota.",
                    "type": "insufficient_quota",
                    "code": "insufficient_quota",
                }
            },
        )

    original_post = httpx.post
    httpx.post = fake_post
    try:
        decision = engine.request_decision(
            {
                "default_symbol": "INFY",
                "candidate_actions": [{"symbol": "INFY", "action": "BUY_STOCK", "instrument_type": "STOCK", "side": "BUY", "score": 0.8}],
                "quotes": {"INFY": {"ltp": 1500.0}},
            },
            db_session,
        )
    finally:
        httpx.post = original_post

    assert decision.action == "HOLD"
    assert decision.rationale_points == ["OpenAI API quota exceeded for the configured project."]


def test_llm_falls_back_to_anthropic_when_openai_fails(db_session, monkeypatch) -> None:
    engine = LLMDecisionEngine()
    engine.settings.llm_api_key = "openai-key"
    engine.settings.anthropic_api_key = "anthropic-key"
    engine.settings.anthropic_model = "claude-sonnet-4-20250514"
    engine.settings.gemini_api_key = None
    monkeypatch.setattr("app.llm.service.get_runtime_settings", lambda db=None: engine.settings)

    valid_response = json.dumps(
        {
            "decision": "BUY_STOCK",
            "symbol": "INFY",
            "instrument_type": "STOCK",
            "action": "BUY_STOCK",
            "side": "BUY",
            "quantity": 1,
            "entry_type": "MARKET",
            "entry_price_hint": 1500.0,
            "stop_loss": 1480.0,
            "take_profit": 1530.0,
            "max_holding_minutes": 240,
            "confidence": 0.81,
            "rationale_points": ["Fallback provider selected the strongest valid candidate."],
            "invalidation_condition": "Momentum weakens materially.",
            "risk_level": "MEDIUM",
        }
    )

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: ANN001,ANN201
        del json, timeout
        request = httpx.Request("POST", url, headers=headers)
        auth_header = headers.get("Authorization", "")
        if auth_header == "Bearer openai-key":
            return httpx.Response(
                429,
                request=request,
                json={
                    "error": {
                        "message": "You exceeded your current quota.",
                        "type": "insufficient_quota",
                        "code": "insufficient_quota",
                    }
                },
            )
        response = Mock()
        response.raise_for_status = Mock()
        response.json = Mock(return_value={"choices": [{"message": {"content": valid_response}}]})
        return response

    original_post = httpx.post
    httpx.post = fake_post
    try:
        decision = engine.request_decision(
            {
                "default_symbol": "INFY",
                "candidate_actions": [{"symbol": "INFY", "action": "BUY_STOCK", "instrument_type": "STOCK", "side": "BUY", "score": 0.8}],
                "quotes": {"INFY": {"ltp": 1500.0}},
            },
            db_session,
        )
    finally:
        httpx.post = original_post

    assert decision.action == "BUY_STOCK"
    assert decision.confidence == 0.81


def test_gpt5_openai_request_omits_temperature(db_session, monkeypatch) -> None:
    engine = LLMDecisionEngine()
    engine.settings.llm_api_key = "openai-key"
    engine.settings.llm_model = "gpt-5-mini"
    engine.settings.anthropic_api_key = None
    engine.settings.gemini_api_key = None
    monkeypatch.setattr("app.llm.service.get_runtime_settings", lambda db=None: engine.settings)

    captured_json = {}
    valid_response = json.dumps(
        {
            "decision": "BUY_STOCK",
            "symbol": "INFY",
            "instrument_type": "STOCK",
            "action": "BUY_STOCK",
            "side": "BUY",
            "quantity": 1,
            "entry_type": "MARKET",
            "entry_price_hint": 1500.0,
            "stop_loss": 1480.0,
            "take_profit": 1530.0,
            "max_holding_minutes": 240,
            "confidence": 0.81,
            "rationale_points": ["OpenAI primary provider returned valid JSON."],
            "invalidation_condition": "Momentum weakens materially.",
            "risk_level": "MEDIUM",
        }
    )

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: ANN001,ANN201
        del url, headers, timeout
        captured_json.update(json or {})
        response = Mock()
        response.raise_for_status = Mock()
        response.json = Mock(return_value={"choices": [{"message": {"content": valid_response}}]})
        return response

    original_post = httpx.post
    httpx.post = fake_post
    try:
        decision = engine.request_decision(
            {
                "default_symbol": "INFY",
                "candidate_actions": [{"symbol": "INFY", "action": "BUY_STOCK", "instrument_type": "STOCK", "side": "BUY", "score": 0.8}],
                "quotes": {"INFY": {"ltp": 1500.0}},
            },
            db_session,
        )
    finally:
        httpx.post = original_post

    assert decision.action == "BUY_STOCK"
    assert "temperature" not in captured_json


def test_llm_normalizes_recommendation_bundle_to_app_schema(db_session, monkeypatch) -> None:
    engine = LLMDecisionEngine()
    engine.settings.llm_api_key = "openai-key"
    engine.settings.anthropic_api_key = None
    engine.settings.gemini_api_key = None
    monkeypatch.setattr("app.llm.service.get_runtime_settings", lambda db=None: engine.settings)
    bundle_response = json.dumps(
        {
            "default_symbol": "HDFCBANK",
            "overall_recommendation": "HOLD",
            "confidence": 0.15,
            "notes": "Capital preservation is preferred while evidence is weak.",
            "recommendations": [
                {
                    "symbol": "HDFCBANK",
                    "action": "HOLD",
                    "side": "BUY",
                    "entry_type": "MARKET",
                    "confidence": 0.18,
                    "rationale": "Trend is weak and the market is sideways.",
                    "suggested_order": None,
                    "suggested_position_size": 0.0,
                    "risk_management": "Remain flat until a clearer setup appears.",
                }
            ],
            "follow_up_recommendations": ["Re-evaluate if momentum improves."],
        }
    )

    def fake_post(*args, **kwargs):  # noqa: ANN002,ANN003
        response = Mock()
        response.raise_for_status = Mock()
        response.json = Mock(return_value={"choices": [{"message": {"content": bundle_response}}]})
        return response

    original_post = httpx.post
    httpx.post = fake_post
    try:
        decision = engine.request_decision(
            {
                "default_symbol": "HDFCBANK",
                "candidate_actions": [{"symbol": "HDFCBANK", "action": "HOLD", "instrument_type": "STOCK", "side": "BUY", "score": 0.1}],
                "quotes": {"HDFCBANK": {"ltp": 758.45}},
            },
            db_session,
        )
    finally:
        httpx.post = original_post

    assert decision.action == "HOLD"
    assert decision.symbol == "HDFCBANK"
    assert decision.instrument_type == "STOCK"
    assert decision.quantity == 0
    assert decision.entry_price_hint == 758.45
    assert decision.rationale_points[0] == "Capital preservation is preferred while evidence is weak."


def test_llm_transport_timeout_does_not_retry_same_provider(db_session, monkeypatch) -> None:
    engine = LLMDecisionEngine()
    engine.settings.llm_api_key = "openai-key"
    engine.settings.anthropic_api_key = None
    engine.settings.gemini_api_key = None
    monkeypatch.setattr("app.llm.service.get_runtime_settings", lambda db=None: engine.settings)

    call_count = 0

    def fake_post(*args, **kwargs):  # noqa: ANN002,ANN003
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("The read operation timed out")

    original_post = httpx.post
    httpx.post = fake_post
    try:
        decision = engine.request_decision(
            {
                "default_symbol": "INFY",
                "candidate_actions": [{"symbol": "INFY", "action": "BUY_STOCK", "instrument_type": "STOCK", "side": "BUY", "score": 0.8}],
                "quotes": {"INFY": {"ltp": 1500.0}},
            },
            db_session,
        )
    finally:
        httpx.post = original_post

    assert decision.action == "HOLD"
    assert call_count == 1


def test_llm_falls_back_to_gemini_when_openai_and_claude_fail(db_session, monkeypatch) -> None:
    engine = LLMDecisionEngine()
    engine.settings.llm_api_key = "openai-key"
    engine.settings.anthropic_api_key = "anthropic-key"
    engine.settings.gemini_api_key = "gemini-key"
    engine.settings.gemini_api_base = "https://generativelanguage.googleapis.com/v1beta/openai"
    engine.settings.gemini_model = "gemini-3-flash-preview"
    monkeypatch.setattr("app.llm.service.get_runtime_settings", lambda db=None: engine.settings)

    valid_response = json.dumps(
        {
            "decision": "BUY_STOCK",
            "symbol": "INFY",
            "instrument_type": "STOCK",
            "action": "BUY_STOCK",
            "side": "BUY",
            "quantity": 1,
            "entry_type": "MARKET",
            "entry_price_hint": 1500.0,
            "stop_loss": 1488.0,
            "take_profit": 1532.0,
            "max_holding_minutes": 240,
            "confidence": 0.79,
            "rationale_points": ["Gemini supplied the final valid fallback response."],
            "invalidation_condition": "Momentum weakens materially.",
            "risk_level": "MEDIUM",
        }
    )

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: ANN001,ANN201
        del json, timeout
        request = httpx.Request("POST", url, headers=headers)
        auth_header = headers.get("Authorization", "")
        if auth_header == "Bearer openai-key":
            return httpx.Response(
                429,
                request=request,
                json={"error": {"message": "quota", "type": "insufficient_quota", "code": "insufficient_quota"}},
            )
        if auth_header == "Bearer anthropic-key":
            return httpx.Response(
                500,
                request=request,
                json={"error": {"message": "upstream issue"}},
            )
        response = Mock()
        response.raise_for_status = Mock()
        response.json = Mock(return_value={"choices": [{"message": {"content": valid_response}}]})
        return response

    original_post = httpx.post
    httpx.post = fake_post
    try:
        decision = engine.request_decision(
            {
                "default_symbol": "INFY",
                "candidate_actions": [{"symbol": "INFY", "action": "BUY_STOCK", "instrument_type": "STOCK", "side": "BUY", "score": 0.8}],
                "quotes": {"INFY": {"ltp": 1500.0}},
            },
            db_session,
        )
    finally:
        httpx.post = original_post

    assert decision.action == "BUY_STOCK"
    assert decision.confidence == 0.79
