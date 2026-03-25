from __future__ import annotations

from types import SimpleNamespace

from app.services.marketaux_service import NewsFetchResult
from app.services.marketaux_service import MarketauxService, _MARKETAUX_CACHE
from app.services.news_service import NewsService


def test_news_service_uses_technical_only_mode_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.news_service.MarketauxService.fetch_news",
        lambda self, symbols, force_refresh=False: NewsFetchResult(
            items=[],
            feed_status="disabled",
            technical_only_reason="Marketaux API key is not configured, so the board is using technical history only.",
        ),
    )

    service = NewsService()
    summary = service.summarize(["INFY"])

    assert summary.items == []
    assert summary.overall_sentiment == 0.0
    assert summary.technical_only is True
    assert summary.feed_status == "disabled"
    assert summary.technical_only_reason is not None


def test_marketaux_service_uses_shared_cache_until_manual_refresh(monkeypatch) -> None:
    call_count = {"value": 0}
    _MARKETAUX_CACHE.clear()

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {
                        "title": "INFY gains",
                        "description": "Growth update",
                        "source": "wire",
                        "published_at": "2026-03-25T09:30:00",
                        "url": f"https://example.com/{call_count['value']}",
                        "entities": [{"symbol": "INFY"}],
                    }
                ]
            }

    def fake_get(*args, **kwargs):
        call_count["value"] += 1
        return DummyResponse()

    monkeypatch.setattr(
        "app.services.marketaux_service.get_runtime_settings",
        lambda: SimpleNamespace(
            marketaux_api_key="test-key",
            marketaux_base_url="https://example.com/news",
        ),
    )
    monkeypatch.setattr("app.services.marketaux_service.httpx.get", fake_get)

    service = MarketauxService()
    first = service.fetch_news(["INFY"])
    second = service.fetch_news(["INFY"])
    refreshed = service.fetch_news(["INFY"], force_refresh=True)

    assert first.feed_status == "live"
    assert second.feed_status == "live"
    assert refreshed.feed_status == "live"
    assert call_count["value"] == 2
