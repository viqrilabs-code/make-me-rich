from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.schemas.news import NewsItemResponse, NewsSummaryResponse
from app.services.marketaux_service import MarketauxService


POSITIVE_WORDS = {"beat", "growth", "expands", "surge", "upgrade", "bullish", "profit"}
NEGATIVE_WORDS = {"miss", "cuts", "falls", "risk", "downgrade", "bearish", "loss"}


class NewsService:
    def __init__(self) -> None:
        self.marketaux = MarketauxService()

    def get_relevant_news(self, symbols: list[str], force_refresh: bool = False) -> list[NewsItemResponse]:
        return self._normalize_items(self.marketaux.fetch_news(symbols, force_refresh=force_refresh).items, symbols)

    def summarize(self, symbols: list[str], force_refresh: bool = False) -> NewsSummaryResponse:
        fetch_result = self.marketaux.fetch_news(symbols, force_refresh=force_refresh)
        items = self._normalize_items(fetch_result.items, symbols)
        counts = Counter(symbol for item in items for symbol in item.symbols)
        overall = 0.0
        if items:
            overall = sum(item.sentiment_score for item in items) / len(items)
        return NewsSummaryResponse(
            items=items,
            overall_sentiment=round(overall, 2),
            top_symbols=[
                {"symbol": symbol, "articles": count}
                for symbol, count in counts.most_common(5)
            ],
            feed_status=fetch_result.feed_status,
            technical_only=not items,
            technical_only_reason=fetch_result.technical_only_reason if not items else None,
        )

    def _normalize_items(self, raw_items: list[dict], symbols: list[str]) -> list[NewsItemResponse]:
        seen: set[str] = set()
        items: list[NewsItemResponse] = []
        tracked = {symbol.upper() for symbol in symbols}
        for raw in raw_items:
            url = raw.get("url") or raw.get("uuid") or raw.get("title")
            if not url or url in seen:
                continue
            seen.add(url)

            title = raw.get("title", "")
            description = raw.get("description")
            entities = raw.get("entities") or []
            article_symbols = sorted(
                {entity.get("symbol", "").upper() for entity in entities if entity.get("symbol")}
            )
            if not article_symbols:
                text = f"{title} {description or ''}".upper()
                article_symbols = sorted(symbol for symbol in tracked if symbol in text)
            relevance = 0.4 + min(len(article_symbols), 3) * 0.2
            sentiment = self._sentiment_score(f"{title} {description or ''}")
            published_at = datetime.fromisoformat(
                raw.get("published_at", datetime.utcnow().isoformat())
            )
            items.append(
                NewsItemResponse(
                    title=title,
                    description=description,
                    source=raw.get("source", "unknown"),
                    published_at=published_at,
                    url=url,
                    symbols=article_symbols,
                    sentiment_score=round(sentiment, 2),
                    relevance_score=round(min(relevance, 1.0), 2),
                )
            )
        return sorted(items, key=lambda item: item.published_at, reverse=True)

    def _sentiment_score(self, text: str) -> float:
        words = {part.strip(".,!?").lower() for part in text.split()}
        score = sum(1 for word in words if word in POSITIVE_WORDS)
        score -= sum(1 for word in words if word in NEGATIVE_WORDS)
        return max(min(score / 3, 1.0), -1.0)
