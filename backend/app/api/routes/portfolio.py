from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import DailyPerformance
from app.schemas.portfolio import DailyPerformanceResponse, OverviewResponse, PortfolioSnapshotResponse
from app.services.dashboard_service import build_latest_snapshot, build_overview, refresh_live_portfolio_cache


router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/latest", response_model=PortfolioSnapshotResponse | None)
def latest_portfolio(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> PortfolioSnapshotResponse | None:
    snapshot = build_latest_snapshot(db)
    db.commit()
    return snapshot


@router.get("/performance", response_model=list[DailyPerformanceResponse])
def portfolio_performance(
    limit: int = Query(default=30, ge=1, le=365),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DailyPerformanceResponse]:
    refresh_live_portfolio_cache(db)
    db.commit()
    rows = db.scalars(
        select(DailyPerformance).order_by(DailyPerformance.trading_date.desc()).limit(limit)
    ).all()
    return [DailyPerformanceResponse.model_validate(row) for row in reversed(rows)]


@router.get("/overview", response_model=OverviewResponse)
def portfolio_overview(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> OverviewResponse:
    overview = build_overview(db)
    db.commit()
    return overview
