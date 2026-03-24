from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any

import httpx

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


@dataclass(slots=True)
class ResolvedInstrument:
    requested_symbol: str
    display_symbol: str
    security_id: str
    exchange: str
    segment: str
    scrip_code: str
    instrument_type: str
    raw_payload: dict[str, Any]


class INDMoneyAdapter(BrokerAdapter):
    broker_name = "indmoney"

    ENDPOINTS: dict[str, str] = {
        "account": "/funds",
        "positions": "/portfolio/positions",
        "holdings": "/portfolio/holdings",
        "orders": "/order-book",
        "quotes": "/market/quotes/full",
        "candles": "/market/historical/{interval}",
        "place_order": "/order",
        "modify_order": "/order/modify",
        "cancel_order": "/order/cancel",
        "margin": "/funds",
        "profile": "/user/profile",
        "trades": "/trades/{order_id}",
        "instruments": "/market/instruments",
    }

    INTERVAL_MAP: dict[str, str] = {
        "1m": "1minute",
        "2m": "2minute",
        "5m": "5minute",
        "15m": "15minute",
        "30m": "30minute",
        "60m": "60minute",
        "1h": "60minute",
        "1d": "1day",
        "1w": "1week",
        "1mo": "1month",
    }

    STATUS_MAP: dict[str, str] = {
        "SUCCESS": "filled",
        "PARTIALLY FILLED": "partially_filled",
        "PARTIALLY FILLED - CANCELLED": "partially_filled_cancelled",
        "PARTIALLY FILLED - EXPIRED": "partially_filled_expired",
        "MODIFIED": "modified",
        "CANCELLED": "cancelled",
        "FAILED": "failed",
        "ABORTED": "failed",
        "EXPIRED": "expired",
        "O-PENDING": "pending",
        "SL-PENDING": "pending",
        "PENDING": "pending",
        "PROCESSING": "pending",
        "INITIATED": "pending",
        "QUEUED": "pending",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.indmoney_base_url.rstrip("/"),
            timeout=15.0,
            headers={
                "Authorization": settings.indmoney_api_key or "",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )
        self._instrument_cache: dict[str, list[dict[str, str]]] = {}
        self._resolution_cache: dict[tuple[str, str | None], ResolvedInstrument] = {}

    def get_account(self) -> BrokerAccount:
        funds = self._get_funds()
        opening_balance = (
            self._to_float(funds.get("sod_balance"))
            + self._to_float(funds.get("funds_added"))
            - self._to_float(funds.get("funds_withdrawn"))
        )
        realized_pnl = self._to_float(funds.get("realized_pnl"))
        unrealized_pnl = self._to_float(funds.get("unrealized_pnl"))
        cash_balance = max(
            self._to_float(funds.get("withdrawal_balance")),
            self._to_float(funds.get("sod_balance")),
            0.0,
        )
        total_equity = max(opening_balance + realized_pnl + unrealized_pnl, cash_balance)
        margin_available = self._extract_available_balance(funds)
        return BrokerAccount(
            cash_balance=cash_balance,
            total_equity=total_equity,
            margin_available=margin_available,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            source="indstocks",
            raw_payload={
                "funds": funds,
                "equity_inference": "sod_balance + funds_added - funds_withdrawn + realized_pnl + unrealized_pnl",
            },
        )

    def get_positions(self) -> list[BrokerPosition]:
        positions: list[BrokerPosition] = []
        seen: set[tuple[str, str, str]] = set()
        for segment, product in (
            ("derivative", "margin"),
            ("derivative", "intraday"),
            ("equity", "cnc"),
            ("equity", "intraday"),
        ):
            payload = self._request_json(
                "GET",
                self.ENDPOINTS["positions"],
                params={"segment": segment, "product": product},
            )
            data = payload if isinstance(payload, dict) else {}
            entries = list(data.get("net_positions", [])) + list(data.get("day_positions", []))
            for item in entries:
                quantity = abs(self._to_float(item.get("net_quantity") or item.get("quantity")))
                if quantity <= 0:
                    continue
                security_id = str(item.get("security_id") or "")
                product_key = f"{segment}:{product}"
                dedupe_key = (security_id, product_key, str(item.get("position_type") or "open"))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                side = "BUY" if self._to_float(item.get("net_quantity") or item.get("quantity")) >= 0 else "SELL"
                symbol = self._display_symbol(
                    str(item.get("trading_symbol") or item.get("name") or item.get("security_id") or "UNKNOWN")
                )
                positions.append(
                    BrokerPosition(
                        symbol=symbol,
                        instrument_type=self._infer_instrument_type_from_text(str(item.get("trading_symbol") or symbol)),
                        side=side,
                        quantity=quantity,
                        avg_price=self._to_float(item.get("average_price")),
                        current_price=self._to_float(item.get("last_traded_price")),
                        unrealized_pnl=self._to_float(item.get("pnl_absolute")),
                        broker_position_id=security_id or None,
                        mode="live",
                        raw_payload={**item, "segment": segment, "product": product},
                    )
                )
        return positions

    def get_holdings(self) -> list[BrokerPosition]:
        payload = self._request_json("GET", self.ENDPOINTS["holdings"])
        data = payload if isinstance(payload, list) else []
        holdings: list[BrokerPosition] = []
        for item in data:
            holdings.append(
                BrokerPosition(
                    symbol=self._display_symbol(str(item.get("trading_symbol") or item.get("security_id") or "UNKNOWN")),
                    instrument_type="STOCK",
                    side="BUY",
                    quantity=self._to_float(item.get("quantity")),
                    avg_price=self._to_float(item.get("average_price")),
                    current_price=self._to_float(item.get("last_traded_price")),
                    unrealized_pnl=self._to_float(item.get("pnl_absolute")),
                    broker_position_id=str(item.get("security_id") or "") or None,
                    mode="live",
                    raw_payload=item,
                )
            )
        return holdings

    def get_orders(self) -> list[BrokerOrder]:
        payload = self._request_json("GET", self.ENDPOINTS["orders"])
        data = payload if isinstance(payload, list) else []
        orders: list[BrokerOrder] = []
        for item in data:
            order_id = str(item.get("id") or item.get("order_id") or "")
            status = self._normalize_order_status(str(item.get("status") or "pending"))
            orders.append(
                BrokerOrder(
                    broker_order_id=order_id or None,
                    client_order_id=order_id or "indstocks_order",
                    symbol=self._display_symbol(str(item.get("name") or item.get("security_id") or "UNKNOWN")),
                    instrument_type=self._infer_instrument_type_from_text(str(item.get("name") or item.get("order_type") or "")),
                    side=str(item.get("txn_type") or "BUY").upper(),
                    order_type=str(item.get("order_type") or "MARKET").upper(),
                    quantity=self._to_float(item.get("requested_qty") or item.get("qty")),
                    price=self._to_optional_float(item.get("requested_price")),
                    trigger_price=self._to_optional_float(item.get("sl_trigger_price")),
                    status=status,
                    fill_price=self._to_optional_float(item.get("traded_price")),
                    fill_quantity=self._to_optional_float(item.get("traded_qty")),
                    placed_at=self._parse_datetime(item.get("created_at")),
                    updated_at=self._parse_datetime(item.get("updated_at")),
                    mode="live",
                    raw_payload=item,
                )
            )
        return orders

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        if not symbols:
            return []
        resolved = [self._resolve_symbol(symbol) for symbol in symbols]
        quote_data = self._request_json(
            "GET",
            self.ENDPOINTS["quotes"],
            params={"scrip-codes": ",".join(item.scrip_code for item in resolved)},
        )
        data = quote_data if isinstance(quote_data, dict) else {}
        timestamp = datetime.now(timezone.utc)
        quotes: list[Quote] = []
        for item in resolved:
            raw = data.get(item.scrip_code)
            if not raw:
                continue
            bid, ask = self._extract_bid_ask(raw)
            quotes.append(
                Quote(
                    symbol=item.requested_symbol,
                    ltp=self._to_float(raw.get("live_price") or raw.get("ltp")),
                    bid=bid,
                    ask=ask,
                    timestamp=timestamp,
                    volume=self._to_optional_float(raw.get("volume")),
                )
            )
        return quotes

    def get_candles(self, symbol: str, interval: str, lookback: int) -> list[Candle]:
        return self.get_candles_batch([symbol], interval, lookback).get(symbol.strip().upper(), [])

    def get_candles_batch(self, symbols: list[str], interval: str, lookback: int) -> dict[str, list[Candle]]:
        if not symbols:
            return {}
        resolved = [self._resolve_symbol(symbol) for symbol in symbols]
        mapped_interval = self.INTERVAL_MAP.get(interval.lower(), interval)
        now = datetime.now(timezone.utc)
        step = self._interval_timedelta(mapped_interval)
        start = now - step * max(lookback + 5, 10)
        payload = self._request_json(
            "GET",
            self.ENDPOINTS["candles"].format(interval=mapped_interval),
            params={
                "scrip-codes": ",".join(item.scrip_code for item in resolved),
                "start_time": self._to_epoch_ms(start),
                "end_time": self._to_epoch_ms(now),
            },
        )
        data = payload if isinstance(payload, dict) else {}
        return {
            item.requested_symbol: self._parse_candles(
                (data.get(item.scrip_code) or {}).get("candles", []),
                lookback,
            )
            for item in resolved
        }

    def place_order(self, order_request: OrderRequest) -> BrokerOrder:
        order_type = order_request.order_type.upper()
        if order_type not in {"MARKET", "LIMIT"}:
            raise ValueError(
                "INDstocks normal orders in this adapter support MARKET and LIMIT only. "
                "Use advisory or paper mode for unsupported order types until smart-order wiring is added."
            )

        instrument = self._resolve_symbol(order_request.symbol, order_request.instrument_type)
        quantity = int(round(order_request.quantity))
        if quantity <= 0:
            raise ValueError("Quantity must be at least 1 for INDstocks order placement.")

        request_payload: dict[str, Any] = {
            "txn_type": order_request.side.upper(),
            "exchange": instrument.exchange,
            "segment": instrument.segment,
            "product": self._infer_product(order_request, instrument),
            "order_type": order_type,
            "validity": "DAY",
            "security_id": instrument.security_id,
            "qty": quantity,
            "is_amo": False,
            "algo_id": "99999",
        }
        if order_type == "LIMIT":
            request_payload["limit_price"] = order_request.price

        response_payload = self._request_json("POST", self.ENDPOINTS["place_order"], json=request_payload)
        response = response_payload if isinstance(response_payload, dict) else {}
        order_id = str(response.get("order_id") or "")
        status = self._normalize_order_status(str(response.get("order_status") or "pending"))
        fill_price, fill_quantity, trades = self._fetch_trade_fill_details(order_id, status)
        now = datetime.now(timezone.utc)
        return BrokerOrder(
            broker_order_id=order_id or None,
            client_order_id=order_request.client_order_id,
            symbol=order_request.symbol.upper(),
            instrument_type=order_request.instrument_type,
            side=order_request.side.upper(),
            order_type=order_type,
            quantity=float(quantity),
            price=order_request.price,
            trigger_price=order_request.trigger_price,
            status=status,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            placed_at=now,
            updated_at=now,
            mode=order_request.mode,
            raw_payload={
                "request": request_payload,
                "response": response,
                "instrument": instrument.raw_payload,
                "trades": trades,
                "requested_stop_loss": order_request.stop_loss,
                "requested_take_profit": order_request.take_profit,
                "note": "Protective stop-loss and take-profit are tracked by the app unless wired via broker smart-order APIs.",
            },
        )

    def modify_order(self, order_id: str, payload: dict[str, Any]) -> BrokerOrder:
        segment = self._infer_segment_from_payload(payload)
        request_payload: dict[str, Any] = {
            "order_id": order_id,
            "segment": segment,
        }
        if payload.get("quantity") is not None:
            request_payload["qty"] = int(round(float(payload["quantity"])))
        if payload.get("price") is not None:
            request_payload["limit_price"] = float(payload["price"])

        self._request_json("POST", self.ENDPOINTS["modify_order"], json=request_payload)
        for order in self.get_orders():
            if order.broker_order_id == order_id:
                return order

        now = datetime.now(timezone.utc)
        return BrokerOrder(
            broker_order_id=order_id,
            client_order_id=str(payload.get("client_order_id") or order_id),
            symbol=str(payload.get("symbol") or "UNKNOWN"),
            instrument_type=str(payload.get("instrument_type") or "STOCK"),
            side=str(payload.get("side") or "BUY").upper(),
            order_type=str(payload.get("order_type") or "LIMIT").upper(),
            quantity=float(payload.get("quantity") or 0.0),
            price=float(payload["price"]) if payload.get("price") is not None else None,
            trigger_price=float(payload["trigger_price"]) if payload.get("trigger_price") is not None else None,
            status="modified",
            fill_price=None,
            fill_quantity=None,
            placed_at=now,
            updated_at=now,
            mode=str(payload.get("mode") or "live"),
            raw_payload={"request": request_payload},
        )

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        request_payload = {"order_id": order_id, "segment": "DERIVATIVE" if order_id.upper().startswith("DRV-") else "EQUITY"}
        response = self._request_json("POST", self.ENDPOINTS["cancel_order"], json=request_payload)
        return {
            "order_id": order_id,
            "status": "cancelled",
            "request": request_payload,
            "response": response,
        }

    def get_margin(self) -> BrokerMargin:
        funds = self._get_funds()
        available = self._extract_available_balance(funds)
        account = self.get_account()
        return BrokerMargin(
            available=available,
            utilized=max(account.total_equity - available, 0.0),
            leverage_enabled=any(
                self._to_float(value) > 0
                for key, value in dict(funds.get("detailed_avl_balance") or {}).items()
                if key.lower() in {"future", "option_sell", "eq_mis", "eq_mtf"}
            ),
        )

    def healthcheck(self) -> BrokerHealth:
        configured = bool(self.settings.indmoney_api_key)
        if not configured:
            return BrokerHealth(
                broker=self.broker_name,
                healthy=False,
                message="INDstocks access token missing. Set INDMONEY_API_KEY from the INDstocks dashboard.",
                details={"configured": False, "base_url": self.settings.indmoney_base_url},
            )

        try:
            payload = self._request_json("GET", self.ENDPOINTS["profile"])
            profile = payload.get("user", payload) if isinstance(payload, dict) else {}
            return BrokerHealth(
                broker=self.broker_name,
                healthy=True,
                message="INDstocks API token validated.",
                details={
                    "configured": True,
                    "base_url": self.settings.indmoney_base_url,
                    "user_id": profile.get("id") or profile.get("user_id"),
                    "display_name": profile.get("display_name") or profile.get("name"),
                    "plan_type": profile.get("plan_type"),
                },
            )
        except Exception as exc:
            return BrokerHealth(
                broker=self.broker_name,
                healthy=False,
                message="INDstocks healthcheck failed.",
                details={
                    "configured": True,
                    "base_url": self.settings.indmoney_base_url,
                    "error": str(exc),
                },
            )

    def _get_funds(self) -> dict[str, Any]:
        payload = self._request_json("GET", self.ENDPOINTS["account"])
        return payload if isinstance(payload, dict) else {}

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        self._require_token()
        response = self.client.request(method, path, params=params, json=json)
        response.raise_for_status()
        payload = response.json()
        success = payload.get("status") == "success" or payload.get("success") is True
        if not success:
            message = payload.get("message") or payload.get("error_code") or "INDstocks request failed."
            raise RuntimeError(message)
        return payload.get("data")

    def _request_csv(self, path: str, *, params: dict[str, Any]) -> list[dict[str, str]]:
        self._require_token()
        response = self.client.get(path, params=params, headers={"Accept": "text/csv"})
        response.raise_for_status()
        reader = csv.DictReader(StringIO(response.text.lstrip("\ufeff")))
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {str(key or "").strip().upper(): str(value or "").strip() for key, value in row.items()}
            if any(cleaned.values()):
                rows.append(cleaned)
        return rows

    def _require_token(self) -> None:
        if not self.settings.indmoney_api_key:
            raise RuntimeError("INDstocks access token missing. Set INDMONEY_API_KEY before using the live adapter.")

    def _resolve_symbol(self, symbol: str, instrument_type: str | None = None) -> ResolvedInstrument:
        normalized_symbol = symbol.strip().upper()
        instrument_key = instrument_type.upper() if instrument_type else None
        cache_key = (normalized_symbol, instrument_key)
        if cache_key in self._resolution_cache:
            return self._resolution_cache[cache_key]

        direct = self._resolve_direct_scrip(normalized_symbol, instrument_key)
        if direct:
            self._resolution_cache[cache_key] = direct
            return direct

        if instrument_key in {None, "", "STOCK"}:
            resolved = self._resolve_from_instruments(normalized_symbol, "equity", instrument_key or "STOCK")
            self._resolution_cache[cache_key] = resolved
            return resolved

        resolved = self._resolve_from_instruments(normalized_symbol, "fno", instrument_key)
        self._resolution_cache[cache_key] = resolved
        return resolved

    def _resolve_direct_scrip(self, symbol: str, instrument_type: str | None) -> ResolvedInstrument | None:
        if "_" not in symbol:
            return None
        prefix, security_id = symbol.split("_", 1)
        prefix = prefix.upper()
        if prefix not in {"NSE", "BSE", "NFO", "BFO"} or not security_id.isdigit():
            return None
        if prefix in {"NFO", "BFO"}:
            segment = "DERIVATIVE"
            exchange = "NSE" if prefix == "NFO" else "BSE"
            inferred_type = instrument_type or "FUTURE"
        else:
            segment = "EQUITY"
            exchange = prefix
            inferred_type = instrument_type or "STOCK"
        return ResolvedInstrument(
            requested_symbol=symbol,
            display_symbol=symbol,
            security_id=security_id,
            exchange=exchange,
            segment=segment,
            scrip_code=f"{prefix}_{security_id}",
            instrument_type=inferred_type,
            raw_payload={"direct_symbol": True},
        )

    def _resolve_from_instruments(
        self,
        symbol: str,
        source: str,
        instrument_type: str,
    ) -> ResolvedInstrument:
        rows = self._get_instruments(source)
        normalized_lookup = self._normalize_lookup(symbol)
        for row in rows:
            if normalized_lookup in self._instrument_lookup_keys(row):
                resolved = self._instrument_from_row(symbol, row, instrument_type if source == "fno" else "STOCK")
                if source == "fno" and instrument_type != resolved.instrument_type:
                    continue
                return resolved

        if source == "fno":
            raise ValueError(
                "INDstocks derivative trading requires an explicit tradable contract symbol or scrip-code "
                "(for example NIFTY25MAYFUT or NFO_51011)."
            )
        raise ValueError(f"Unable to resolve INDstocks instrument for symbol '{symbol}'.")

    def _get_instruments(self, source: str) -> list[dict[str, str]]:
        if source not in self._instrument_cache:
            self._instrument_cache[source] = self._request_csv(
                self.ENDPOINTS["instruments"],
                params={"source": source, "format": "csv"},
            )
        return self._instrument_cache[source]

    def _instrument_lookup_keys(self, row: dict[str, str]) -> set[str]:
        keys = {
            row.get("SYMBOL_NAME", ""),
            row.get("TRADING_SYMBOL", ""),
            row.get("CUSTOM_SYMBOL", ""),
            row.get("UNDERLYING_SYMBOL", ""),
            row.get("ISIN", ""),
            row.get("SECURITY_ID", ""),
        }
        return {self._normalize_lookup(value) for value in keys if value}

    def _instrument_from_row(
        self,
        requested_symbol: str,
        row: dict[str, str],
        instrument_type: str,
    ) -> ResolvedInstrument:
        security_id = row.get("SECURITY_ID")
        if not security_id:
            raise ValueError(f"Instrument row for '{requested_symbol}' is missing SECURITY_ID.")
        exchange = self._infer_exchange(row, instrument_type)
        segment = "EQUITY" if instrument_type == "STOCK" else "DERIVATIVE"
        quote_prefix = self._quote_prefix(exchange, segment)
        trading_symbol = row.get("TRADING_SYMBOL") or row.get("CUSTOM_SYMBOL") or row.get("SYMBOL_NAME") or requested_symbol
        return ResolvedInstrument(
            requested_symbol=requested_symbol,
            display_symbol=self._display_symbol(trading_symbol),
            security_id=security_id,
            exchange=exchange,
            segment=segment,
            scrip_code=f"{quote_prefix}_{security_id}",
            instrument_type=instrument_type if instrument_type != "STOCK" else self._infer_instrument_type_from_row(row),
            raw_payload=row,
        )

    def _fetch_trade_fill_details(self, order_id: str, status: str) -> tuple[float | None, float | None, list[dict[str, Any]]]:
        if not order_id or status not in {"filled", "partially_filled"}:
            return None, None, []
        try:
            payload = self._request_json("GET", self.ENDPOINTS["trades"].format(order_id=order_id))
        except Exception:
            return None, None, []
        trades = payload if isinstance(payload, list) else []
        total_qty = sum(self._to_float(item.get("quantity")) for item in trades)
        if total_qty <= 0:
            return None, None, trades
        total_notional = sum(self._to_float(item.get("quantity")) * self._to_float(item.get("price")) for item in trades)
        return total_notional / total_qty, total_qty, trades

    def _extract_available_balance(self, funds: dict[str, Any]) -> float:
        detailed = dict(funds.get("detailed_avl_balance") or {})
        balances = [self._to_float(value) for value in detailed.values()]
        balances.extend(
            [
                self._to_float(funds.get("withdrawal_balance")),
                self._to_float(funds.get("sod_balance")),
            ]
        )
        return max(balances or [0.0])

    def _extract_bid_ask(self, quote: dict[str, Any]) -> tuple[float | None, float | None]:
        market_depth = quote.get("market_depth") or {}
        depth = market_depth.get("depth") or []
        if not depth:
            return None, None
        first_level = depth[0] if isinstance(depth[0], dict) else {}
        buy = first_level.get("buy") or {}
        sell = first_level.get("sell") or {}
        return self._to_optional_float(buy.get("price")), self._to_optional_float(sell.get("price"))

    def _infer_product(self, order_request: OrderRequest, instrument: ResolvedInstrument) -> str:
        if instrument.instrument_type == "STOCK":
            return "CNC" if order_request.mode == "live" else "INTRADAY"
        return "MARGIN"

    def _infer_segment_from_payload(self, payload: dict[str, Any]) -> str:
        symbol = str(payload.get("symbol") or "")
        instrument_type = str(payload.get("instrument_type") or "").upper()
        if instrument_type in {"CALL", "PUT", "FUTURE"}:
            return "DERIVATIVE"
        if symbol.upper().startswith(("NFO_", "BFO_")):
            return "DERIVATIVE"
        return "EQUITY"

    def _infer_exchange(self, row: dict[str, str], instrument_type: str) -> str:
        exchange = (row.get("EXCH") or row.get("EXCHANGE") or "").upper()
        if exchange in {"NSE", "BSE"}:
            return exchange
        return "NSE" if instrument_type in {"CALL", "PUT", "FUTURE"} else "NSE"

    def _quote_prefix(self, exchange: str, segment: str) -> str:
        if segment == "DERIVATIVE":
            return "BFO" if exchange == "BSE" else "NFO"
        return exchange

    def _infer_instrument_type_from_row(self, row: dict[str, str]) -> str:
        joined = " ".join(
            value
            for value in (
                row.get("OPTION_TYPE"),
                row.get("TRADING_SYMBOL"),
                row.get("CUSTOM_SYMBOL"),
                row.get("SYMBOL_NAME"),
            )
            if value
        )
        return self._infer_instrument_type_from_text(joined)

    def _infer_instrument_type_from_text(self, value: str) -> str:
        normalized = value.upper()
        if "CALL" in normalized or normalized.endswith("CE") or " CE" in normalized:
            return "CALL"
        if "PUT" in normalized or normalized.endswith("PE") or " PE" in normalized:
            return "PUT"
        if "FUT" in normalized:
            return "FUTURE"
        return "STOCK"

    def _normalize_order_status(self, status: str) -> str:
        normalized = status.strip().upper()
        return self.STATUS_MAP.get(normalized, normalized.lower() or "pending")

    def _display_symbol(self, value: str) -> str:
        text = value.strip().upper()
        if text.endswith("-EQ"):
            return text[:-3]
        return text

    def _normalize_lookup(self, value: str) -> str:
        return "".join(character for character in value.upper() if character.isalnum())

    def _parse_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return self._parse_timestamp(value)
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

    def _parse_timestamp(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc)

    def _interval_timedelta(self, interval: str) -> timedelta:
        return {
            "1minute": timedelta(minutes=1),
            "2minute": timedelta(minutes=2),
            "5minute": timedelta(minutes=5),
            "15minute": timedelta(minutes=15),
            "30minute": timedelta(minutes=30),
            "60minute": timedelta(hours=1),
            "1day": timedelta(days=1),
            "1week": timedelta(weeks=1),
            "1month": timedelta(days=30),
        }.get(interval, timedelta(minutes=5))

    def _parse_candles(self, rows: list[Any], lookback: int) -> list[Candle]:
        return [
            Candle(
                timestamp=self._parse_timestamp(row["ts"]),
                open=self._to_float(row["o"]),
                high=self._to_float(row["h"]),
                low=self._to_float(row["l"]),
                close=self._to_float(row["c"]),
                volume=self._to_optional_float(row.get("v")),
            )
            for row in rows[-lookback:]
            if isinstance(row, dict) and {"ts", "o", "h", "l", "c"} <= set(row)
        ]

    def _to_epoch_ms(self, value: datetime) -> int:
        return int(value.timestamp() * 1000)

    def _to_float(self, value: Any) -> float:
        optional = self._to_optional_float(value)
        return optional if optional is not None else 0.0

    def _to_optional_float(self, value: Any) -> float | None:
        if value in {None, "", "null"}:
            return None
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None
