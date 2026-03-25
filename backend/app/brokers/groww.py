from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any
import warnings

from app.brokers.base import BrokerAdapter
from app.brokers.types import (
    BrokerAccount,
    BrokerHealth,
    BrokerMargin,
    BrokerOrder,
    BrokerPosition,
    Candle,
    OrderRequest,
    Quote,
)
from app.core.config import Settings

try:
    from growwapi import GrowwAPI
except Exception:  # noqa: BLE001
    GrowwAPI = None


@dataclass(slots=True)
class ResolvedInstrument:
    requested_symbol: str
    display_symbol: str
    groww_symbol: str
    exchange: str
    segment: str
    instrument_type: str
    raw_payload: dict[str, Any]


class GrowwAdapter(BrokerAdapter):
    broker_name = "groww"

    INTERVAL_MAP: dict[str, str] = {
        "1m": "1minute",
        "2m": "2minute",
        "5m": "5minute",
        "10m": "10minute",
        "15m": "15minute",
        "30m": "30minute",
        "60m": "1hour",
        "1h": "1hour",
        "4h": "4hour",
        "1d": "1day",
        "1w": "1week",
        "1mo": "1month",
    }

    STATUS_MAP: dict[str, str] = {
        "OPEN": "pending",
        "PENDING": "pending",
        "PARTIALLY_EXECUTED": "partially_filled",
        "COMPLETED": "filled",
        "EXECUTED": "filled",
        "REJECTED": "failed",
        "CANCELLED": "cancelled",
        "EXPIRED": "expired",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sdk = None
        self._access_token: str | None = None
        self._instrument_rows: list[dict[str, str]] | None = None
        self._resolution_cache: dict[tuple[str, str | None], ResolvedInstrument] = {}

    def get_account(self) -> BrokerAccount:
        margin = self.get_margin()
        holdings = self.get_holdings()
        positions = self.get_positions()
        cash_balance = margin.available
        holdings_value = sum(max(item.current_price, 0.0) * item.quantity for item in holdings)
        positions_unrealized = sum(item.unrealized_pnl for item in positions if item.instrument_type != "STOCK")
        realized_pnl = sum(self._to_float(item.raw_payload.get("realised_pnl")) for item in positions)
        unrealized_pnl = sum(item.unrealized_pnl for item in holdings) + positions_unrealized
        total_equity = max(cash_balance + holdings_value + positions_unrealized, cash_balance)
        return BrokerAccount(
            cash_balance=round(cash_balance, 2),
            total_equity=round(total_equity, 2),
            margin_available=round(margin.available, 2),
            realized_pnl=round(realized_pnl, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            source="groww",
            raw_payload={
                "holdings_count": len(holdings),
                "positions_count": len(positions),
                "margin": margin.model_dump(),
            },
        )

    def get_positions(self) -> list[BrokerPosition]:
        payload = self._client().get_positions_for_user()
        rows = list(payload.get("positions", []))
        symbols = [str(row.get("trading_symbol") or "").strip().upper() for row in rows if row.get("trading_symbol")]
        quotes = self._quotes_map(symbols)

        positions: list[BrokerPosition] = []
        for row in rows:
            symbol = str(row.get("trading_symbol") or "").strip().upper()
            if not symbol:
                continue
            raw_qty = self._to_float(row.get("quantity"))
            if raw_qty == 0:
                continue
            avg_price = self._to_float(row.get("net_price") or row.get("net_carry_forward_price"))
            quote = quotes.get(symbol)
            current_price = quote.ltp if quote else avg_price
            side = "BUY" if raw_qty >= 0 else "SELL"
            quantity = abs(raw_qty)
            try:
                resolved = self._resolve_symbol(symbol)
                instrument_type = resolved.instrument_type
            except Exception:  # noqa: BLE001
                instrument_type = self._infer_instrument_type_from_text(symbol)

            unrealized = self._to_optional_float(row.get("unrealised_pnl"))
            if unrealized is None:
                if side == "BUY":
                    unrealized = (current_price - avg_price) * quantity
                else:
                    unrealized = (avg_price - current_price) * quantity

            positions.append(
                BrokerPosition(
                    symbol=symbol,
                    instrument_type=instrument_type,
                    side=side,
                    quantity=quantity,
                    avg_price=avg_price,
                    current_price=current_price,
                    unrealized_pnl=round(unrealized, 2),
                    broker_position_id=str(row.get("groww_position_id") or row.get("symbol_isin") or "") or None,
                    mode="live",
                    raw_payload=row,
                )
            )
        return positions

    def get_holdings(self) -> list[BrokerPosition]:
        payload = self._client().get_holdings_for_user()
        rows = list(payload.get("holdings", []))
        symbols = [str(row.get("trading_symbol") or "").strip().upper() for row in rows if row.get("trading_symbol")]
        quotes = self._quotes_map(symbols)

        holdings: list[BrokerPosition] = []
        for row in rows:
            symbol = str(row.get("trading_symbol") or "").strip().upper()
            if not symbol:
                continue
            quantity = self._to_float(row.get("quantity"))
            avg_price = self._to_float(row.get("average_price"))
            quote = quotes.get(symbol)
            current_price = quote.ltp if quote else avg_price
            unrealized = (current_price - avg_price) * quantity
            holdings.append(
                BrokerPosition(
                    symbol=symbol,
                    instrument_type="STOCK",
                    side="BUY",
                    quantity=quantity,
                    avg_price=avg_price,
                    current_price=current_price,
                    unrealized_pnl=round(unrealized, 2),
                    broker_position_id=str(row.get("isin") or "") or None,
                    mode="live",
                    raw_payload=row,
                )
            )
        return holdings

    def get_orders(self) -> list[BrokerOrder]:
        payload = self._client().get_order_list(page=0, page_size=100)
        rows = list(payload.get("order_list", []))
        orders: list[BrokerOrder] = []
        for row in rows:
            status = self.STATUS_MAP.get(str(row.get("order_status") or "").upper(), "pending")
            orders.append(
                BrokerOrder(
                    broker_order_id=str(row.get("groww_order_id") or "") or None,
                    client_order_id=str(row.get("order_reference_id") or row.get("groww_order_id") or "groww_order"),
                    symbol=str(row.get("trading_symbol") or "UNKNOWN").upper(),
                    instrument_type=self._infer_instrument_type_from_text(str(row.get("trading_symbol") or "")),
                    side=str(row.get("transaction_type") or "BUY").upper(),
                    order_type=str(row.get("order_type") or "MARKET").upper(),
                    quantity=self._to_float(row.get("quantity")),
                    price=self._to_optional_float(row.get("price")),
                    trigger_price=self._to_optional_float(row.get("trigger_price")),
                    status=status,
                    fill_price=self._to_optional_float(row.get("average_fill_price")),
                    fill_quantity=self._to_optional_float(row.get("filled_quantity")),
                    placed_at=self._parse_datetime(row.get("created_at")),
                    updated_at=self._parse_datetime(row.get("exchange_time") or row.get("created_at")),
                    mode="live",
                    raw_payload=row,
                )
            )
        return orders

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        quotes: list[Quote] = []
        for symbol in symbols:
            resolved = self._resolve_symbol(symbol)
            quotes.append(self._fetch_quote_for_resolved(self._client(), resolved))
        return quotes

    def get_quotes_batch(self, symbols: list[str], max_workers: int = 18) -> dict[str, Quote]:
        resolved_rows: list[ResolvedInstrument] = []
        for symbol in list(dict.fromkeys(symbols)):
            try:
                resolved_rows.append(self._resolve_symbol(symbol))
            except Exception:
                continue
        if not resolved_rows:
            return {}

        def worker(resolved: ResolvedInstrument) -> Quote:
            return self._fetch_quote_for_resolved(self._spawn_worker_client(), resolved)

        quotes: dict[str, Quote] = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(resolved_rows))) as executor:
            futures = {executor.submit(worker, resolved): resolved.requested_symbol for resolved in resolved_rows}
            for future in as_completed(futures):
                try:
                    quote = future.result()
                except Exception:
                    continue
                quotes[quote.symbol] = quote
        return quotes

    def get_candles(self, symbol: str, interval: str, lookback: int) -> list[Candle]:
        resolved = self._resolve_symbol(symbol)
        return self._fetch_candles_for_resolved(self._client(), resolved, interval=interval, lookback=lookback)

    def get_candles_batch(
        self,
        symbols: list[str],
        *,
        interval: str = "5m",
        lookback: int = 50,
        max_workers: int = 12,
    ) -> dict[str, list[Candle]]:
        resolved_rows: list[ResolvedInstrument] = []
        for symbol in list(dict.fromkeys(symbols)):
            try:
                resolved_rows.append(self._resolve_symbol(symbol))
            except Exception:
                continue
        if not resolved_rows:
            return {}

        def worker(resolved: ResolvedInstrument) -> tuple[str, list[Candle]]:
            candles = self._fetch_candles_for_resolved(
                self._spawn_worker_client(),
                resolved,
                interval=interval,
                lookback=lookback,
            )
            return resolved.requested_symbol, candles

        candles_map: dict[str, list[Candle]] = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(resolved_rows))) as executor:
            futures = {executor.submit(worker, resolved): resolved.requested_symbol for resolved in resolved_rows}
            for future in as_completed(futures):
                try:
                    symbol, candles = future.result()
                except Exception:
                    continue
                candles_map[symbol] = candles
        return candles_map

    def place_order(self, order_request: OrderRequest) -> BrokerOrder:
        resolved = self._resolve_symbol(order_request.symbol, order_request.instrument_type)
        if order_request.instrument_type in {"CALL", "PUT", "FUTURE"} and resolved.display_symbol == order_request.symbol.upper():
            raise ValueError(
                "Groww derivative execution requires an explicit tradable contract symbol. "
                "Use advisory or paper mode until contract-to-order execution wiring is added."
            )

        response = self._client().place_order(
            trading_symbol=resolved.display_symbol,
            quantity=max(int(round(order_request.quantity)), 1),
            validity=GrowwAPI.VALIDITY_DAY,
            exchange=resolved.exchange,
            segment=resolved.segment,
            product=self._product_for_request(order_request, resolved),
            order_type=self._order_type(order_request.order_type),
            transaction_type=order_request.side.upper(),
            order_reference_id=order_request.client_order_id,
            price=order_request.price or 0.0,
            trigger_price=order_request.trigger_price,
        )
        order_id = str(response.get("groww_order_id") or "")
        status_payload = self._client().get_order_status(groww_order_id=order_id, segment=resolved.segment)
        trade_payload = self._client().get_trade_list_for_order(groww_order_id=order_id, segment=resolved.segment)
        trades = list(trade_payload.get("trade_list", []))
        fill_price = self._trade_fill_price(trades)
        fill_quantity = self._trade_fill_quantity(trades) or self._to_optional_float(status_payload.get("filled_quantity"))
        status = self.STATUS_MAP.get(str(status_payload.get("order_status") or "").upper(), "pending")
        now = datetime.now(timezone.utc)
        return BrokerOrder(
            broker_order_id=order_id or None,
            client_order_id=order_request.client_order_id,
            symbol=resolved.display_symbol,
            instrument_type=order_request.instrument_type,
            side=order_request.side.upper(),
            order_type=self._order_type(order_request.order_type),
            quantity=float(max(int(round(order_request.quantity)), 1)),
            price=order_request.price,
            trigger_price=order_request.trigger_price,
            status=status,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            placed_at=now,
            updated_at=now,
            mode=order_request.mode,
            raw_payload={
                "place_order": response,
                "status": status_payload,
                "trades": trades,
                "instrument": resolved.raw_payload,
            },
        )

    def modify_order(self, order_id: str, payload: dict[str, Any]) -> BrokerOrder:
        segment = self._segment_for_payload(payload)
        quantity = max(int(round(float(payload.get("quantity") or 0))), 1)
        order_type = self._order_type(str(payload.get("order_type") or "LIMIT"))
        response = self._client().modify_order(
            groww_order_id=order_id,
            segment=segment,
            order_type=order_type,
            quantity=quantity,
            price=self._to_optional_float(payload.get("price")),
            trigger_price=self._to_optional_float(payload.get("trigger_price")),
        )
        status_payload = self._client().get_order_status(groww_order_id=order_id, segment=segment)
        now = datetime.now(timezone.utc)
        return BrokerOrder(
            broker_order_id=order_id,
            client_order_id=str(payload.get("client_order_id") or order_id),
            symbol=str(payload.get("symbol") or "UNKNOWN").upper(),
            instrument_type=str(payload.get("instrument_type") or "STOCK").upper(),
            side=str(payload.get("side") or "BUY").upper(),
            order_type=order_type,
            quantity=float(quantity),
            price=self._to_optional_float(payload.get("price")),
            trigger_price=self._to_optional_float(payload.get("trigger_price")),
            status=self.STATUS_MAP.get(str(status_payload.get("order_status") or "").upper(), "modified"),
            fill_price=None,
            fill_quantity=self._to_optional_float(status_payload.get("filled_quantity")),
            placed_at=now,
            updated_at=now,
            mode=str(payload.get("mode") or "live"),
            raw_payload={"modify_response": response, "status": status_payload},
        )

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        segment = self._segment_for_order(order_id)
        response = self._client().cancel_order(groww_order_id=order_id, segment=segment)
        return {"order_id": order_id, "status": "cancelled", "response": response}

    def get_margin(self) -> BrokerMargin:
        payload = self._client().get_available_margin_details()
        fno = dict(payload.get("fno_margin_details") or {})
        equity = dict(payload.get("equity_margin_details") or {})
        available = max(
            self._to_float(payload.get("clear_cash")),
            self._to_float(fno.get("future_balance_available")),
            self._to_float(fno.get("option_buy_balance_available")),
            self._to_float(equity.get("cnc_balance_available")),
            self._to_float(equity.get("mis_balance_available")),
        )
        utilized = max(
            self._to_float(payload.get("net_margin_used")),
            self._to_float(fno.get("net_fno_margin_used")),
            self._to_float(equity.get("net_equity_margin_used")),
            0.0,
        )
        return BrokerMargin(
            available=round(available, 2),
            utilized=round(utilized, 2),
            leverage_enabled=True,
        )

    def healthcheck(self) -> BrokerHealth:
        if not (self.settings.groww_api_key or "").strip():
            return BrokerHealth(
                broker=self.broker_name,
                healthy=False,
                message="Groww API key or access token missing. Set GROWW_API_KEY in Strategy or .env.",
                details={"configured": False},
            )
        try:
            profile = self._client().get_user_profile()
            return BrokerHealth(
                broker=self.broker_name,
                healthy=True,
                message="Groww API credentials validated.",
                details={
                    "configured": True,
                    "ucc": profile.get("ucc"),
                    "vendor_user_id": profile.get("vendor_user_id"),
                    "active_segments": profile.get("active_segments", []),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return BrokerHealth(
                broker=self.broker_name,
                healthy=False,
                message="Groww healthcheck failed.",
                details={"configured": True, "error": str(exc)},
            )

    def _client(self):
        if self._sdk is not None:
            return self._sdk
        if GrowwAPI is None:
            raise RuntimeError("growwapi package is not installed. Add it to backend requirements before using Groww.")

        token_or_key = (self.settings.groww_api_key or "").strip()
        secret = (self.settings.groww_api_secret or "").strip()
        if not token_or_key:
            raise RuntimeError("Groww API key or access token is missing.")

        access_token = token_or_key
        with redirect_stdout(StringIO()):
            if secret:
                access_token = GrowwAPI.get_access_token(api_key=token_or_key, secret=secret)
            self._access_token = access_token
            self._sdk = GrowwAPI(access_token)
        return self._sdk

    def _spawn_worker_client(self):
        if GrowwAPI is None:
            raise RuntimeError("growwapi package is not installed. Add it to backend requirements before using Groww.")
        if self._access_token is None:
            self._client()
        with redirect_stdout(StringIO()):
            return GrowwAPI(self._access_token)

    def _get_instruments(self) -> list[dict[str, str]]:
        if self._instrument_rows is not None:
            return self._instrument_rows
        rows = self._client().get_all_instruments().to_dict("records")
        self._instrument_rows = [
            {str(key or "").upper(): "" if value is None else str(value).strip() for key, value in row.items()}
            for row in rows
        ]
        return self._instrument_rows

    def _resolve_symbol(self, symbol: str, instrument_type: str | None = None) -> ResolvedInstrument:
        normalized_symbol = symbol.strip().upper()
        instrument_key = instrument_type.upper() if instrument_type else None
        cache_key = (normalized_symbol, instrument_key)
        if cache_key in self._resolution_cache:
            return self._resolution_cache[cache_key]

        rows = self._get_instruments()
        candidates: list[tuple[int, dict[str, str]]] = []
        for row in rows:
            if self._normalize_lookup(normalized_symbol) not in self._instrument_lookup_keys(row):
                continue
            inferred = self._infer_instrument_type_from_row(row)
            if instrument_key and instrument_key not in {"STOCK", inferred} and not (
                instrument_key == "STOCK" and inferred == "STOCK"
            ):
                continue
            if not instrument_key and row.get("SEGMENT", "").upper() == "FNO" and normalized_symbol == row.get("UNDERLYING_SYMBOL", "").upper():
                continue
            candidates.append((self._resolution_score(normalized_symbol, instrument_key or "STOCK", row), row))

        if not candidates:
            raise ValueError(f"Unable to resolve Groww instrument for symbol '{symbol}'.")

        candidates.sort(key=lambda item: item[0], reverse=True)
        resolved = self._instrument_from_row(normalized_symbol, candidates[0][1])
        self._resolution_cache[cache_key] = resolved
        return resolved

    def _resolution_score(self, normalized_symbol: str, instrument_type: str, row: dict[str, str]) -> int:
        score = 0
        if row.get("EXCHANGE", "").upper() == "NSE":
            score += 50
        if row.get("TRADING_SYMBOL", "").upper() == normalized_symbol:
            score += 30
        if row.get("SEGMENT", "").upper() == ("CASH" if instrument_type == "STOCK" else "FNO"):
            score += 20
        if self._infer_instrument_type_from_row(row) == instrument_type:
            score += 10
        return score

    def _instrument_lookup_keys(self, row: dict[str, str]) -> set[str]:
        values = {
            row.get("TRADING_SYMBOL", ""),
            row.get("GROWW_SYMBOL", ""),
            row.get("INTERNAL_TRADING_SYMBOL", ""),
            row.get("NAME", ""),
            row.get("UNDERLYING_SYMBOL", ""),
            row.get("EXCHANGE_TOKEN", ""),
        }
        return {self._normalize_lookup(value) for value in values if value}

    def _instrument_from_row(self, requested_symbol: str, row: dict[str, str]) -> ResolvedInstrument:
        return ResolvedInstrument(
            requested_symbol=requested_symbol,
            display_symbol=row.get("TRADING_SYMBOL", requested_symbol),
            groww_symbol=row.get("GROWW_SYMBOL", requested_symbol),
            exchange=row.get("EXCHANGE", "NSE").upper(),
            segment=row.get("SEGMENT", "CASH").upper(),
            instrument_type=self._infer_instrument_type_from_row(row),
            raw_payload=row,
        )

    def _infer_instrument_type_from_row(self, row: dict[str, str]) -> str:
        instrument_type = row.get("INSTRUMENT_TYPE", "").upper()
        if instrument_type == "CE":
            return "CALL"
        if instrument_type == "PE":
            return "PUT"
        if instrument_type == "FUT":
            return "FUTURE"
        return "STOCK"

    def _infer_instrument_type_from_text(self, value: str) -> str:
        normalized = value.upper()
        if normalized.endswith("CE") or " CE" in normalized:
            return "CALL"
        if normalized.endswith("PE") or " PE" in normalized:
            return "PUT"
        if "FUT" in normalized:
            return "FUTURE"
        return "STOCK"

    def _quotes_map(self, symbols: list[str]) -> dict[str, Quote]:
        if not symbols:
            return {}
        return {quote.symbol: quote for quote in self.get_quotes(list(dict.fromkeys(symbols)))}

    def _fetch_quote_for_resolved(self, client, resolved: ResolvedInstrument) -> Quote:
        payload = client.get_quote(
            trading_symbol=resolved.display_symbol,
            exchange=resolved.exchange,
            segment=resolved.segment,
        )
        last_price = self._to_float(payload.get("last_price"))
        bid = self._to_optional_float(payload.get("bid_price"))
        ask = self._to_optional_float(payload.get("offer_price"))
        return Quote(
            symbol=resolved.requested_symbol,
            ltp=last_price,
            bid=bid,
            ask=ask,
            timestamp=self._parse_timestamp(payload.get("last_trade_time")),
            volume=self._to_optional_float(payload.get("volume")),
        )

    def _fetch_candles_for_resolved(
        self,
        client,
        resolved: ResolvedInstrument,
        *,
        interval: str,
        lookback: int,
    ) -> list[Candle]:
        mapped_interval = self.INTERVAL_MAP.get(interval.lower(), "1day")
        step = self._interval_timedelta(mapped_interval)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - (step * max(lookback + 5, 10))
        start_text = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_text = end_time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            payload = client.get_historical_candles(
                exchange=resolved.exchange,
                segment=resolved.segment,
                groww_symbol=resolved.groww_symbol,
                start_time=start_text,
                end_time=end_text,
                candle_interval=mapped_interval,
            )
            rows = list(payload.get("candles", []))
        except Exception as exc:  # noqa: BLE001
            if "Access forbidden for this request" not in str(exc):
                raise
            interval_minutes = self._interval_minutes(mapped_interval)
            if interval_minutes is None:
                raise
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                payload = client.get_historical_candle_data(
                    trading_symbol=resolved.display_symbol,
                    exchange=resolved.exchange,
                    segment=resolved.segment,
                    start_time=start_text,
                    end_time=end_text,
                    interval_in_minutes=interval_minutes,
                )
            rows = list(payload.get("candles", []))
        candles: list[Candle] = []
        for item in rows[-lookback:]:
            if not isinstance(item, list) or len(item) < 6:
                continue
            candles.append(
                Candle(
                    timestamp=self._parse_candle_time(item[0]),
                    open=self._to_float(item[1]),
                    high=self._to_float(item[2]),
                    low=self._to_float(item[3]),
                    close=self._to_float(item[4]),
                    volume=self._to_optional_float(item[5]),
                )
            )
        return candles

    def _order_type(self, value: str) -> str:
        normalized = value.strip().upper()
        if normalized in {"MARKET", "LIMIT"}:
            return normalized
        if normalized in {"STOP_LIMIT", "STOP_LOSS"}:
            return GrowwAPI.ORDER_TYPE_STOP_LOSS
        return GrowwAPI.ORDER_TYPE_MARKET

    def _product_for_request(self, order_request: OrderRequest, resolved: ResolvedInstrument) -> str:
        if resolved.segment == "CASH":
            return GrowwAPI.PRODUCT_CNC if order_request.mode == "live" else GrowwAPI.PRODUCT_MIS
        return GrowwAPI.PRODUCT_MIS if order_request.mode == "paper" else GrowwAPI.PRODUCT_NRML

    def _segment_for_payload(self, payload: dict[str, Any]) -> str:
        instrument_type = str(payload.get("instrument_type") or "").upper()
        return "FNO" if instrument_type in {"CALL", "PUT", "FUTURE"} else "CASH"

    def _segment_for_order(self, order_id: str) -> str:
        for order in self.get_orders():
            if order.broker_order_id == order_id:
                return "FNO" if order.instrument_type in {"CALL", "PUT", "FUTURE"} else "CASH"
        return "CASH"

    def _trade_fill_price(self, trades: list[dict[str, Any]]) -> float | None:
        total_quantity = sum(self._to_float(item.get("quantity")) for item in trades)
        if total_quantity <= 0:
            return None
        total_notional = sum(self._to_float(item.get("quantity")) * self._to_float(item.get("price")) for item in trades)
        return round(total_notional / total_quantity, 2)

    def _trade_fill_quantity(self, trades: list[dict[str, Any]]) -> float | None:
        total_quantity = sum(self._to_float(item.get("quantity")) for item in trades)
        return total_quantity or None

    def _parse_timestamp(self, value: Any) -> datetime:
        if value in (None, ""):
            return datetime.now(timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        return self._parse_datetime(value)

    def _parse_candle_time(self, value: Any) -> datetime:
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric = numeric / 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc)

    def _parse_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _interval_timedelta(self, interval: str) -> timedelta:
        return {
            "1minute": timedelta(minutes=1),
            "2minute": timedelta(minutes=2),
            "5minute": timedelta(minutes=5),
            "10minute": timedelta(minutes=10),
            "15minute": timedelta(minutes=15),
            "30minute": timedelta(minutes=30),
            "1hour": timedelta(hours=1),
            "4hour": timedelta(hours=4),
            "1day": timedelta(days=1),
            "1week": timedelta(days=7),
            "1month": timedelta(days=30),
        }.get(interval, timedelta(days=1))

    def _interval_minutes(self, interval: str) -> int | None:
        return {
            "1minute": 1,
            "2minute": 2,
            "5minute": 5,
            "10minute": 10,
            "15minute": 15,
            "30minute": 30,
            "1hour": 60,
            "4hour": 240,
            "1day": 1440,
        }.get(interval)

    def _to_float(self, value: Any) -> float:
        optional = self._to_optional_float(value)
        return optional if optional is not None else 0.0

    def _to_optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None

    def _normalize_lookup(self, value: str) -> str:
        return "".join(character for character in value.upper() if character.isalnum())
