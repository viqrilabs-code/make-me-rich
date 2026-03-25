from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Position, StrategyConfig
from app.schemas.news import NewsItemResponse, NewsRefreshRequest, NewsSummaryResponse
from app.services.news_service import NewsService


router = APIRouter(prefix="/api/news", tags=["news"])


def _tracked_symbols(db: Session) -> list[str]:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    open_positions = db.scalars(select(Position).where(Position.status == "open")).all()
    symbols = set(strategy.watchlist_symbols_json if strategy else [])
    symbols.update(position.symbol for position in open_positions)
    return sorted(symbols) or ["RELIANCE", "TCS", "INFY"]


@router.get("", response_model=list[NewsItemResponse])
def list_news(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> list[NewsItemResponse]:
    return NewsService().get_relevant_news(_tracked_symbols(db))


@router.get("/summary", response_model=NewsSummaryResponse)
def news_summary(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> NewsSummaryResponse:
    return NewsService().summarize(_tracked_symbols(db))


@router.post("/refresh", response_model=NewsSummaryResponse)
def refresh_news(
    payload: NewsRefreshRequest | None = None,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NewsSummaryResponse:
    symbols = payload.symbols if payload and payload.symbols else _tracked_symbols(db)
    clean_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    return NewsService().summarize(clean_symbols or _tracked_symbols(db), force_refresh=True)
