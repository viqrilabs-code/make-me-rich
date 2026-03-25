from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import StrategyConfig
from app.schemas.market import BestTradeResponse, DailyTopDealsResponse, RequestedInstrument, TradeSetupResponse
from app.services.credential_service import missing_trade_credentials
from app.services.daily_top_deals_service import get_daily_top_deals_snapshot, refresh_daily_top_deals_snapshot
from app.services.trade_setup_service import build_best_trade_setup, build_trade_setup


router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/trade-setup", response_model=TradeSetupResponse)
def get_trade_setup(
    symbol: str = Query(..., min_length=1, max_length=32),
    instrument: RequestedInstrument = Query(default="stock"),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TradeSetupResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    missing = missing_trade_credentials(db, strategy.selected_broker if strategy else "groww")
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Before fetching trades, provide these keys in Strategy -> API keys: " + " ".join(missing),
        )
    try:
        response = build_trade_setup(
            db,
            symbol=symbol,
            requested_instrument=instrument,
            use_llm=True,
            allow_fallback_broker=False,
        )
        db.commit()
        return response
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="Trade analysis timed out or a provider request failed. Please retry.",
        ) from exc


@router.get("/best-trade", response_model=BestTradeResponse)
def get_best_trade(
    symbol: str = Query(..., min_length=1, max_length=32),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BestTradeResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    missing = missing_trade_credentials(db, strategy.selected_broker if strategy else "groww")
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Before fetching trades, provide these keys in Strategy -> API keys: " + " ".join(missing),
        )
    try:
        response = build_best_trade_setup(db, symbol=symbol, allow_fallback_broker=False)
        db.commit()
        return response
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="Best-trade analysis timed out or a provider request failed. Please retry.",
        ) from exc


@router.get("/daily-top-deals", response_model=DailyTopDealsResponse)
def get_daily_top_deals(
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyTopDealsResponse:
    response = get_daily_top_deals_snapshot(db)
    db.commit()
    return response


@router.post("/daily-top-deals/refresh", response_model=DailyTopDealsResponse)
def refresh_daily_top_deals(
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyTopDealsResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    missing = missing_trade_credentials(db, strategy.selected_broker if strategy else "groww")
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Before running the daily sweep, provide these keys in Strategy -> API keys: " + " ".join(missing),
        )
    try:
        response = refresh_daily_top_deals_snapshot(db)
        db.commit()
        return response
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="Daily top-deals sweep timed out or a provider request failed. Please retry tomorrow.",
        ) from exc
