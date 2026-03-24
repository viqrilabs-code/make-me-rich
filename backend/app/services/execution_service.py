from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brokers.base import BrokerAdapter
from app.brokers.mock import MockBrokerAdapter
from app.brokers.types import BrokerAccount, OrderRequest
from app.db.session import SessionLocal
from app.llm.schemas import LLMDecisionResponse
from app.models import DailyPerformance, Order, PortfolioSnapshot, Position, StrategyConfig
from app.risk.models import RiskEvaluationResult
from app.services.audit_service import add_audit_log, add_risk_event
from app.utils.ids import generate_client_order_id, generate_idempotency_key


logger = logging.getLogger(__name__)


OPENING_ACTIONS = {"BUY_STOCK", "SELL_STOCK", "BUY_CALL", "BUY_PUT", "BUY_FUTURE", "SELL_FUTURE"}


class ExecutionService:
    def __init__(self, broker: BrokerAdapter) -> None:
        self.broker = broker

    def record_snapshot(self, db: Session, account: BrokerAccount, source: str = "scheduler") -> PortfolioSnapshot:
        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc),
            cash_balance=account.cash_balance,
            total_equity=account.total_equity,
            margin_available=account.margin_available,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl,
            source=source,
            raw_payload_json=account.raw_payload,
        )
        db.add(snapshot)
        return snapshot

    def execute(
        self,
        db: Session,
        strategy: StrategyConfig,
        decision: LLMDecisionResponse,
        risk_result: RiskEvaluationResult,
        scheduler_run_id: int | None = None,
    ) -> dict[str, Any]:
        if not risk_result.approved:
            add_risk_event(
                db,
                event_type="trade_rejected",
                severity="warning",
                message="Risk engine rejected trade.",
                metadata={"decision": decision.model_dump(), "reasons": risk_result.rejection_reasons},
            )
            return {"status": "rejected", "reasons": risk_result.rejection_reasons}

        if decision.action == "HOLD" or not risk_result.final_order_payload:
            add_audit_log(
                db,
                category="execution",
                message="Decision recorded without order execution.",
                metadata={"decision": decision.model_dump()},
            )
            return {"status": "hold"}

        if strategy.mode == "advisory":
            add_audit_log(
                db,
                category="execution",
                message="Advisory mode active; suggestion recorded but not executed.",
                metadata={"decision": decision.model_dump(), "payload": risk_result.final_order_payload},
            )
            return {"status": "advisory"}

        payload = risk_result.final_order_payload
        idempotency_key = generate_idempotency_key(
            scheduler_run_id,
            decision.symbol,
            decision.action,
            payload["side"],
            payload["quantity"],
        )
        client_order_id = f"cli_{idempotency_key[:24]}"
        existing = db.scalar(select(Order).where(Order.client_order_id == client_order_id))
        if existing:
            add_audit_log(
                db,
                category="execution",
                message="Duplicate order prevented by idempotency key.",
                metadata={"client_order_id": client_order_id},
            )
            return {"status": "duplicate", "order_id": existing.id}

        order_request = OrderRequest(
            client_order_id=client_order_id,
            idempotency_key=idempotency_key,
            symbol=payload["symbol"],
            instrument_type=payload["instrument_type"],
            side=payload["side"],
            order_type=payload["order_type"],
            quantity=payload["quantity"],
            price=payload.get("price"),
            mode=strategy.mode,
            stop_loss=payload.get("stop_loss"),
            take_profit=payload.get("take_profit"),
        )

        execution_broker: BrokerAdapter = self.broker
        if strategy.mode == "paper":
            execution_broker = MockBrokerAdapter(SessionLocal)

        broker_order = None
        for attempt in range(2):
            try:
                broker_order = execution_broker.place_order(order_request)
                break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning("Transient broker error", extra={"attempt": attempt + 1, "error": str(exc)})
                if attempt == 1:
                    raise

        if broker_order is None:
            return {"status": "failed", "reason": "broker_order_missing"}

        order_row = Order(
            broker_order_id=broker_order.broker_order_id,
            client_order_id=broker_order.client_order_id,
            symbol=broker_order.symbol,
            instrument_type=broker_order.instrument_type,
            side=broker_order.side,
            order_type=broker_order.order_type,
            quantity=broker_order.quantity,
            price=broker_order.price,
            trigger_price=broker_order.trigger_price,
            status=broker_order.status,
            fill_price=broker_order.fill_price,
            fill_quantity=broker_order.fill_quantity,
            placed_at=broker_order.placed_at,
            updated_at=broker_order.updated_at,
            mode=broker_order.mode,
            raw_payload_json={
                **broker_order.raw_payload,
                "scheduler_run_id": scheduler_run_id,
                "decision_action": decision.action,
                "idempotency_key": idempotency_key,
                "execution_broker": execution_broker.broker_name,
            },
        )
        db.add(order_row)
        db.flush()

        if broker_order.status.lower() == "filled":
            self._apply_fill(db, order_row, decision)

        add_audit_log(
            db,
            category="execution",
            message="Order execution attempt recorded.",
            metadata={"order_id": order_row.id, "status": order_row.status},
        )
        return {"status": order_row.status, "order_id": order_row.id}

    def _apply_fill(self, db: Session, order: Order, decision: LLMDecisionResponse) -> None:
        now = datetime.now(timezone.utc)
        existing = db.scalar(
            select(Position)
            .where(Position.symbol == order.symbol, Position.status == "open")
            .order_by(Position.opened_at.desc())
        )

        if decision.action in OPENING_ACTIONS:
            if existing and existing.side == order.side and existing.instrument_type == order.instrument_type:
                total_qty = existing.quantity + (order.fill_quantity or order.quantity)
                weighted_cost = (existing.avg_price * existing.quantity) + (
                    (order.fill_price or 0.0) * (order.fill_quantity or order.quantity)
                )
                existing.quantity = total_qty
                existing.avg_price = weighted_cost / total_qty
                existing.current_price = order.fill_price or existing.current_price
                existing.stop_loss = decision.stop_loss
                existing.take_profit = decision.take_profit
            else:
                db.add(
                    Position(
                        symbol=order.symbol,
                        instrument_type=order.instrument_type,
                        side=order.side,
                        quantity=order.fill_quantity or order.quantity,
                        avg_price=order.fill_price or order.price or 0.0,
                        current_price=order.fill_price or order.price or 0.0,
                        unrealized_pnl=0.0,
                        realized_pnl=0.0,
                        stop_loss=decision.stop_loss,
                        take_profit=decision.take_profit,
                        opened_at=now,
                        closed_at=None,
                        status="open",
                        broker_position_id=order.broker_order_id,
                        mode=order.mode,
                        raw_payload_json=order.raw_payload_json,
                    )
                )
            return

        if not existing:
            return

        close_quantity = min(order.fill_quantity or order.quantity, existing.quantity)
        fill_price = order.fill_price or order.price or existing.current_price
        if existing.side == "BUY":
            realized = (fill_price - existing.avg_price) * close_quantity
        else:
            realized = (existing.avg_price - fill_price) * close_quantity
        existing.quantity -= close_quantity
        existing.realized_pnl += realized
        existing.current_price = fill_price
        if existing.quantity <= 0:
            existing.status = "closed"
            existing.closed_at = now
        self._apply_cooldown_if_needed(db)

    def reconcile_positions(self, db: Session, strategy: StrategyConfig) -> int:
        positions = db.scalars(select(Position).where(Position.status == "open")).all()
        if not positions:
            return 0
        quotes = {quote.symbol: quote for quote in self.broker.get_quotes([item.symbol for item in positions])}
        closed = 0
        for position in positions:
            quote = quotes.get(position.symbol)
            if not quote:
                continue
            position.current_price = quote.ltp
            if position.side == "BUY":
                position.unrealized_pnl = (quote.ltp - position.avg_price) * position.quantity
                stop_hit = position.stop_loss is not None and quote.ltp <= position.stop_loss
                target_hit = position.take_profit is not None and quote.ltp >= position.take_profit
            else:
                position.unrealized_pnl = (position.avg_price - quote.ltp) * position.quantity
                stop_hit = position.stop_loss is not None and quote.ltp >= position.stop_loss
                target_hit = position.take_profit is not None and quote.ltp <= position.take_profit

            if stop_hit or target_hit:
                exit_side = "SELL" if position.side == "BUY" else "BUY"
                order = Order(
                    broker_order_id=f"manual_{generate_client_order_id('recon')}",
                    client_order_id=generate_client_order_id("recon"),
                    symbol=position.symbol,
                    instrument_type=position.instrument_type,
                    side=exit_side,
                    order_type="MARKET",
                    quantity=position.quantity,
                    price=quote.ltp,
                    trigger_price=None,
                    status="filled",
                    fill_price=quote.ltp,
                    fill_quantity=position.quantity,
                    placed_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    mode=strategy.mode,
                    raw_payload_json={"reconciled_exit": True, "reason": "stop" if stop_hit else "target"},
                )
                db.add(order)
                db.flush()
                synthetic = LLMDecisionResponse(
                    decision="EXIT",
                    symbol=position.symbol,
                    instrument_type=position.instrument_type,
                    action="EXIT",
                    side=exit_side,
                    quantity=position.quantity,
                    entry_type="MARKET",
                    entry_price_hint=quote.ltp,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    max_holding_minutes=0,
                    confidence=1.0,
                    rationale_points=["Protective reconciliation close."],
                    invalidation_condition="N/A",
                    risk_level="LOW",
                )
                self._apply_fill(db, order, synthetic)
                closed += 1

        return closed

    def update_daily_performance(self, db: Session) -> DailyPerformance | None:
        today = date.today()
        start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
        snapshots = db.scalars(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.timestamp >= start_of_day)
            .order_by(PortfolioSnapshot.timestamp.asc())
        ).all()
        if not snapshots:
            return None
        opening = snapshots[0].total_equity
        closing = snapshots[-1].total_equity
        trade_count = len(
            db.scalars(
                select(Order).where(Order.placed_at >= start_of_day)
            ).all()
        )
        historical_closes = [row.closing_equity for row in db.scalars(select(DailyPerformance)).all()] + [closing]
        peak = max(historical_closes) if historical_closes else closing
        drawdown = 0.0 if peak == 0 else (peak - closing) / peak * 100

        performance = db.scalar(
            select(DailyPerformance).where(DailyPerformance.trading_date == today)
        )
        if not performance:
            performance = DailyPerformance(
                trading_date=today,
                opening_equity=opening,
                closing_equity=closing,
                realized_pnl=snapshots[-1].realized_pnl,
                unrealized_pnl=snapshots[-1].unrealized_pnl,
                drawdown_pct=drawdown,
                trades_count=trade_count,
            )
            db.add(performance)
        else:
            performance.opening_equity = opening
            performance.closing_equity = closing
            performance.realized_pnl = snapshots[-1].realized_pnl
            performance.unrealized_pnl = snapshots[-1].unrealized_pnl
            performance.drawdown_pct = drawdown
            performance.trades_count = trade_count
        return performance

    def _apply_cooldown_if_needed(self, db: Session) -> None:
        strategy = db.scalar(select(StrategyConfig).limit(1))
        if not strategy:
            return
        closed_positions = db.scalars(
            select(Position)
            .where(Position.status == "closed")
            .order_by(Position.closed_at.desc())
            .limit(strategy.cooldown_after_losses)
        ).all()
        if len(closed_positions) < strategy.cooldown_after_losses:
            return
        if all(position.realized_pnl < 0 for position in closed_positions):
            strategy.cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=strategy.cooldown_minutes)
