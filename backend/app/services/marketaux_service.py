from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.services.credential_service import get_runtime_settings


logger = logging.getLogger(__name__)
_MARKETAUX_CACHE: dict[str, tuple[datetime, "NewsFetchResult"]] = {}
_MARKETAUX_CACHE_LOCK = threading.Lock()


@dataclass(slots=True)
class NewsFetchResult:
    items: list[dict[str, Any]]
    feed_status: str
    technical_only_reason: str | None = None


class MarketauxService:
    def __init__(self) -> None:
        self.settings = get_runtime_settings()

    def fetch_news(self, symbols: list[str], limit: int = 10, force_refresh: bool = False) -> NewsFetchResult:
        cache_key = ",".join(sorted(symbols))
        now = datetime.now(timezone.utc)
        with _MARKETAUX_CACHE_LOCK:
            cached = _MARKETAUX_CACHE.get(cache_key)
        if cached and not force_refresh:
            return cached[1]

        if not self.settings.marketaux_api_key:
            result = NewsFetchResult(
                items=[],
                feed_status="disabled",
                technical_only_reason="Marketaux API key is not configured, so the board is using technical history only.",
            )
            self._store_cache(cache_key, now, result)
            return result

        params = {
            "api_token": self.settings.marketaux_api_key,
            "symbols": ",".join(symbols),
            "limit": limit,
            "language": "en",
            "published_after": (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M"),
            "filter_entities": "true",
        }
        try:
            response = httpx.get(self.settings.marketaux_base_url, params=params, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            items = data.get("data", [])
            result = NewsFetchResult(
                items=items,
                feed_status="live" if items else "empty",
                technical_only_reason=(
                    None
                    if items
                    else "No fresh relevant headlines were returned, so the board is relying on technical history only."
                ),
            )
            self._store_cache(cache_key, now, result)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Marketaux request failed, switching to technical-only mode",
                extra={"error": self._redact_error(str(exc))},
            )
            result = NewsFetchResult(
                items=[],
                feed_status="error",
                technical_only_reason="Live news fetch failed, so the board switched to technical-only analysis.",
            )
            self._store_cache(cache_key, now, result)
            return result

    def _store_cache(self, cache_key: str, fetched_at: datetime, result: NewsFetchResult) -> None:
        with _MARKETAUX_CACHE_LOCK:
            _MARKETAUX_CACHE[cache_key] = (fetched_at, result)

    def _redact_error(self, message: str) -> str:
        secret = self.settings.marketaux_api_key or ""
        if secret:
            message = message.replace(secret, "***")
        return message
