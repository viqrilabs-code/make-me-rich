from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.llm.prompts import build_decision_prompt
from app.llm.schemas import ALLOWED_ACTIONS, LLMDecisionResponse, fallback_hold
from app.models import StrategyConfig
from app.services.audit_service import add_audit_log
from app.services.credential_service import get_runtime_settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LLMProvider:
    name: str
    base_url: str
    api_key: str
    model: str


class LLMDecisionEngine:
    def __init__(self) -> None:
        self.settings = get_runtime_settings()

    def request_decision(self, context: dict[str, Any], db: Session) -> LLMDecisionResponse:
        prompt = build_decision_prompt(context)
        runtime_settings = get_runtime_settings(db)
        preserved_overrides: dict[str, Any] = {}
        for field_name in [
            "llm_api_base",
            "llm_api_key",
            "llm_model",
            "anthropic_api_base",
            "anthropic_api_key",
            "anthropic_model",
            "gemini_api_base",
            "gemini_api_key",
            "gemini_model",
            "llm_timeout_seconds",
            "llm_temperature",
        ]:
            current_value = getattr(self.settings, field_name, None)
            runtime_value = getattr(runtime_settings, field_name, None)
            if current_value not in (None, "") and runtime_value in (None, ""):
                preserved_overrides[field_name] = current_value
        self.settings = runtime_settings.model_copy(update=preserved_overrides)
        add_audit_log(
            db,
            category="llm_prompt",
            message="Decision prompt prepared.",
            metadata={"version": prompt["version"], "prompt": prompt},
        )

        providers = self._provider_chain(db)
        if not providers:
            decision = self._heuristic_decision(context, reason="No configured LLM provider is available.")
            add_audit_log(
                db,
                category="llm_validation",
                message="Using heuristic fallback because no LLM provider is configured.",
                metadata={"decision": decision.model_dump()},
            )
            return decision

        messages = [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ]
        last_error_reason: str | None = None
        for provider_index, provider in enumerate(providers):
            add_audit_log(
                db,
                category="llm_provider",
                message=f"Attempting LLM decision via {provider.name}.",
                metadata={"provider": provider.name, "model": provider.model, "base_url": provider.base_url},
            )

            provider_messages = list(messages)
            for attempt in range(2):
                try:
                    content = self._request_completion(provider, provider_messages)
                    decision = self._parse_decision(content, context)
                    add_audit_log(
                        db,
                        category="llm_response",
                        message="LLM decision validated successfully.",
                        metadata={
                            "provider": provider.name,
                            "model": provider.model,
                            "content": content,
                            "decision": decision.model_dump(),
                        },
                    )
                    return decision
                except Exception as exc:  # noqa: BLE001
                    last_error_reason = self._describe_llm_error(exc, provider)
                    logger.warning(
                        "LLM decision parse failed",
                        extra={
                            "attempt": attempt + 1,
                            "provider": provider.name,
                            "error": str(exc),
                            "reason": last_error_reason,
                        },
                    )
                    if isinstance(exc, (ValueError, KeyError, IndexError, TypeError)):
                        provider_messages = [
                            *provider_messages,
                            {"role": "assistant", "content": "Your previous response was invalid."},
                            {
                                "role": "user",
                                "content": "Return one valid JSON object matching the required schema and choosing only from supplied candidates.",
                            },
                        ]
                        continue
                    break

            if provider_index < len(providers) - 1:
                add_audit_log(
                    db,
                    category="llm_provider",
                    message=f"Falling back from {provider.name} to the next LLM provider.",
                    metadata={"provider": provider.name, "reason": last_error_reason},
                )

        decision = fallback_hold(
            symbol=context.get("default_symbol", "CASH"),
            rationale=last_error_reason or "Invalid LLM output after retry. Fallback to HOLD.",
        )
        add_audit_log(
            db,
            category="llm_validation",
            message="Fallback HOLD used after LLM failure.",
            metadata={"decision": decision.model_dump(), "reason": last_error_reason},
        )
        return decision

    def _provider_chain(self, db: Session) -> list[LLMProvider]:
        preferred_provider = db.scalar(select(StrategyConfig.preferred_llm_provider).limit(1)) or "openai"
        provider_order = []
        for provider_name in [preferred_provider, "openai", "anthropic", "gemini"]:
            if provider_name not in provider_order:
                provider_order.append(provider_name)

        providers: list[LLMProvider] = []
        for provider_name in provider_order:
            if provider_name == "openai" and self.settings.llm_api_key:
                providers.append(
                    LLMProvider(
                        name="openai",
                        base_url=self.settings.llm_api_base,
                        api_key=self.settings.llm_api_key,
                        model=self.settings.llm_model,
                    )
                )
            if provider_name == "anthropic" and self.settings.anthropic_api_key:
                providers.append(
                    LLMProvider(
                        name="anthropic",
                        base_url=self.settings.anthropic_api_base,
                        api_key=self.settings.anthropic_api_key,
                        model=self.settings.anthropic_model,
                    )
                )
            if provider_name == "gemini" and self.settings.gemini_api_key:
                providers.append(
                    LLMProvider(
                        name="gemini",
                        base_url=self.settings.gemini_api_base,
                        api_key=self.settings.gemini_api_key,
                        model=self.settings.gemini_model,
                    )
                )
        return providers

    def _request_completion(self, provider: LLMProvider, messages: list[dict[str, str]]) -> str:
        timeout_seconds = min(float(self.settings.llm_timeout_seconds), 8.0)
        payload = {
            "model": provider.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if not (provider.name == "openai" and provider.model.lower().startswith("gpt-5")):
            payload["temperature"] = self.settings.llm_temperature

        response = httpx.post(
            f"{provider.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {provider.api_key}"},
            json=payload,
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0)),
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _describe_llm_error(self, exc: Exception, provider: LLMProvider) -> str:
        provider_label = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "gemini": "Google Gemini",
        }.get(provider.name, provider.name.title())
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            error_code = None
            error_message = None
            try:
                payload = exc.response.json().get("error", {})
                error_code = payload.get("code") or payload.get("type")
                error_message = payload.get("message")
            except Exception:  # noqa: BLE001
                payload = None

            if status_code == 429 and error_code == "insufficient_quota":
                return f"{provider_label} API quota exceeded for the configured project."
            if status_code == 429:
                return f"{provider_label} API rate limit reached. Back off and retry later."
            if error_message:
                return f"{provider_label} API error ({status_code}): {error_message}"
            return f"{provider_label} API error ({status_code})."

        if isinstance(exc, ValueError):
            if str(exc):
                return str(exc)
            return f"Malformed {provider_label} output after retry."

        return f"{provider_label} request failed: {type(exc).__name__}."

    def _parse_decision(self, raw_content: str, context: dict[str, Any]) -> LLMDecisionResponse:
        cleaned = self._strip_markdown_fences(raw_content)
        try:
            decision = LLMDecisionResponse.model_validate_json(cleaned)
        except Exception:
            payload = json.loads(cleaned)
            decision = self._normalize_decision_payload(payload, context)
        self._validate_against_candidates(decision, context.get("candidate_actions", []))
        return decision

    def _strip_markdown_fences(self, raw_content: str) -> str:
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json", "", 1).strip()
        return cleaned

    def _normalize_decision_payload(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> LLMDecisionResponse:
        recommendations = payload.get("recommendations")
        if isinstance(recommendations, list) and recommendations:
            return self._normalize_recommendation_bundle(payload, context)
        raise ValueError("Malformed LLM output after retry.")

    def _normalize_recommendation_bundle(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> LLMDecisionResponse:
        candidates = context.get("candidate_actions", [])
        recommendations = [item for item in payload.get("recommendations", []) if isinstance(item, dict)]
        selected = self._select_recommendation(recommendations, payload.get("overall_recommendation"), candidates)
        if selected is None:
            raise ValueError("Malformed LLM output after retry.")

        resolved_candidate = self._resolve_candidate_from_recommendation(selected, candidates)
        symbol = resolved_candidate.get("symbol") or selected.get("symbol") or context.get("default_symbol", "CASH")
        action = resolved_candidate.get("action", "HOLD")
        side = resolved_candidate.get("side", str(selected.get("side", "BUY")).upper())
        instrument_type = resolved_candidate.get("instrument_type", "STOCK")
        quote = context.get("quotes", {}).get(symbol, {})
        order_details = selected.get("suggested_order") or {}

        entry_price_hint = self._coerce_float(order_details.get("price"))
        if entry_price_hint is None:
            entry_price_hint = self._coerce_float(selected.get("entry_price_hint"))
        if entry_price_hint is None:
            entry_price_hint = self._coerce_float(quote.get("ltp"))

        stop_loss = self._coerce_float(order_details.get("stop_loss"))
        take_profit = self._coerce_float(order_details.get("take_profit"))
        quantity = self._coerce_float(order_details.get("quantity"))
        if quantity is None:
            quantity = self._coerce_float(selected.get("suggested_position_size"))
        if quantity is None:
            quantity = 0.0 if action == "HOLD" else 1.0
        quantity = max(quantity, 0.0)

        recommendation_confidence = self._coerce_float(selected.get("confidence"))
        overall_confidence = self._coerce_float(payload.get("confidence"))
        confidence = recommendation_confidence if recommendation_confidence is not None else overall_confidence
        if confidence is None:
            confidence = 0.2 if action == "HOLD" else 0.65
        confidence = min(max(confidence, 0.0), 1.0)

        rationale_points = [
            item
            for item in [
                payload.get("notes"),
                selected.get("rationale"),
                selected.get("risk_management"),
            ]
            if isinstance(item, str) and item.strip()
        ]
        if not rationale_points:
            rationale_points = ["Structured recommendation normalized from provider response."]

        invalidation_condition = next(
            (
                item
                for item in payload.get("follow_up_recommendations", [])
                if isinstance(item, str) and item.strip()
            ),
            "A stronger risk-adjusted setup appears.",
        )

        return LLMDecisionResponse(
            decision=action,
            symbol=symbol,
            instrument_type=instrument_type,
            action=action,
            side=side,
            quantity=quantity,
            entry_type=str(selected.get("entry_type") or resolved_candidate.get("entry_type") or "MARKET").upper(),
            entry_price_hint=entry_price_hint,
            stop_loss=stop_loss,
            take_profit=take_profit,
            max_holding_minutes=0 if action == "HOLD" else 240,
            confidence=confidence,
            rationale_points=rationale_points,
            invalidation_condition=invalidation_condition,
            risk_level="LOW" if action == "HOLD" else "MEDIUM",
        )

    def _select_recommendation(
        self,
        recommendations: list[dict[str, Any]],
        overall_recommendation: Any,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        preferred_action = str(overall_recommendation or "").upper().strip()
        ranked = sorted(
            recommendations,
            key=lambda item: self._coerce_float(item.get("confidence")) or 0.0,
            reverse=True,
        )
        if preferred_action:
            for recommendation in ranked:
                if str(recommendation.get("action", "")).upper().strip() == preferred_action:
                    return recommendation
        if ranked:
            return ranked[0]
        if candidates:
            top = candidates[0]
            return {
                "symbol": top.get("symbol"),
                "action": top.get("action"),
                "side": top.get("side", "BUY"),
                "entry_type": top.get("entry_type", "MARKET"),
                "confidence": top.get("score", 0.2),
            }
        return None

    def _resolve_candidate_from_recommendation(
        self,
        recommendation: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        symbol = str(recommendation.get("symbol", "")).upper().strip()
        requested_action = str(recommendation.get("action", "")).upper().strip()
        requested_side = str(recommendation.get("side", "BUY")).upper().strip()
        symbol_candidates = [candidate for candidate in candidates if candidate.get("symbol") == symbol]

        if requested_action in ALLOWED_ACTIONS:
            exact = [
                candidate
                for candidate in symbol_candidates
                if candidate.get("action") == requested_action and candidate.get("side", "BUY") == requested_side
            ]
            if exact:
                return max(exact, key=lambda item: item.get("score", 0))

        if requested_action in {"BUY", "SELL"}:
            directional = [
                candidate
                for candidate in symbol_candidates
                if candidate.get("side", "BUY") == requested_side and candidate.get("action") != "HOLD"
            ]
            if directional:
                return max(directional, key=lambda item: item.get("score", 0))

        hold_candidates = [candidate for candidate in symbol_candidates if candidate.get("action") == "HOLD"]
        if hold_candidates:
            return max(hold_candidates, key=lambda item: item.get("score", 0))

        if symbol_candidates:
            return max(symbol_candidates, key=lambda item: item.get("score", 0))

        return {
            "symbol": symbol or "CASH",
            "action": "HOLD",
            "instrument_type": "STOCK",
            "side": requested_side or "BUY",
            "entry_type": "MARKET",
        }

    def _coerce_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _validate_against_candidates(
        self, decision: LLMDecisionResponse, candidates: list[dict[str, Any]]
    ) -> None:
        allowed = {
            (candidate["symbol"], candidate["action"], candidate["instrument_type"], candidate["side"])
            for candidate in candidates
        }
        key = (decision.symbol, decision.action, decision.instrument_type, decision.side)
        if decision.action == "HOLD":
            return
        if key not in allowed:
            raise ValueError("Decision action not present in supplied candidates.")

    def _heuristic_decision(self, context: dict[str, Any], reason: str) -> LLMDecisionResponse:
        candidates = sorted(
            context.get("candidate_actions", []),
            key=lambda item: item.get("score", 0),
            reverse=True,
        )
        if not candidates:
            return fallback_hold(rationale=reason)

        top = candidates[0]
        if top.get("action") == "HOLD" or top.get("score", 0) < 0.68:
            return fallback_hold(symbol=top.get("symbol", "CASH"), rationale=reason)

        quote = context.get("quotes", {}).get(top["symbol"], {})
        price = quote.get("ltp")
        side = top.get("side", "BUY")
        stop_loss = None
        take_profit = None
        if price:
            if side == "BUY":
                stop_loss = round(price * 0.99, 2)
                take_profit = round(price * 1.02, 2)
            else:
                stop_loss = round(price * 1.01, 2)
                take_profit = round(price * 0.98, 2)

        return LLMDecisionResponse(
            decision=top["action"],
            symbol=top["symbol"],
            instrument_type=top["instrument_type"],
            action=top["action"],
            side=side,
            quantity=1,
            entry_type=top.get("entry_type", "MARKET"),
            entry_price_hint=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            max_holding_minutes=240,
            confidence=min(max(float(top.get("score", 0.7)), 0.0), 1.0),
            rationale_points=[
                reason,
                f"Selected top candidate {top['action']} for {top['symbol']} with score {top.get('score', 0):.2f}.",
            ],
            invalidation_condition="Momentum and news alignment deteriorate.",
            risk_level="MEDIUM",
        )
