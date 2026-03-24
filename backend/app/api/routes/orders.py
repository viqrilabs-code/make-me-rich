from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Order
from app.schemas.order import OrderResponse


router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=list[OrderResponse])
def list_orders(
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrderResponse]:
    orders = db.scalars(select(Order).order_by(Order.placed_at.desc()).limit(limit)).all()
    return [OrderResponse.model_validate(order) for order in orders]


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, _: object = Depends(get_current_user), db: Session = Depends(get_db)) -> OrderResponse:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse.model_validate(order)

