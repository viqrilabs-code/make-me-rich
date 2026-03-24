from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NewsItemResponse(BaseModel):
    title: str
    description: str | None = None
    source: str
    published_at: datetime
    url: str
    symbols: list[str]
    sentiment_score: float
    relevance_score: float


class NewsSummaryResponse(BaseModel):
    items: list[NewsItemResponse]
    overall_sentiment: float
    top_symbols: list[dict]
    feed_status: str = "empty"
    technical_only: bool = False
    technical_only_reason: str | None = None
