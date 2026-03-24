from __future__ import annotations

from app.services.marketaux_service import NewsFetchResult
from app.services.news_service import NewsService


def test_news_service_uses_technical_only_mode_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.news_service.MarketauxService.fetch_news",
        lambda self, symbols: NewsFetchResult(
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
