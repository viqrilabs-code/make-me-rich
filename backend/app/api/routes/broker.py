from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.broker import BrokerAccountResponse, BrokerHealthResponse, BrokerOrderResponse, BrokerPositionResponse
from app.services.broker_service import get_active_broker, get_broker_health, test_broker_connection


router = APIRouter(prefix="/api/broker", tags=["broker"])


@router.get("/health", response_model=BrokerHealthResponse)
def broker_health(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> BrokerHealthResponse:
    adapter, selected, using_fallback = get_active_broker(db)
    health = adapter.healthcheck()
    return BrokerHealthResponse(
        broker=health.broker,
        healthy=health.healthy,
        message=health.message,
        active_broker=selected,
        using_fallback=using_fallback,
        details=health.details,
    )


@router.get("/account", response_model=BrokerAccountResponse)
def broker_account(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> BrokerAccountResponse:
    adapter, _, _ = get_active_broker(db)
    account = adapter.get_account()
    return BrokerAccountResponse(**account.model_dump())


@router.get("/positions", response_model=list[BrokerPositionResponse])
def broker_positions(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> list[BrokerPositionResponse]:
    adapter, _, _ = get_active_broker(db)
    return [BrokerPositionResponse(**position.model_dump()) for position in adapter.get_positions()]


@router.get("/orders", response_model=list[BrokerOrderResponse])
def broker_orders(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> list[BrokerOrderResponse]:
    adapter, _, _ = get_active_broker(db)
    return [BrokerOrderResponse(**order.model_dump()) for order in adapter.get_orders()]


@router.post("/test-connection", response_model=BrokerHealthResponse)
def broker_test_connection(
    broker_name: str | None = Query(default=None),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BrokerHealthResponse:
    health = test_broker_connection(db, broker_name=broker_name)
    return BrokerHealthResponse(
        broker=health.broker,
        healthy=health.healthy,
        message=health.message,
        active_broker=health.broker,
        using_fallback=False,
        details=health.details,
    )
