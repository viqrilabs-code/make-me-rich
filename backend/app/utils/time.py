from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_ist(value: datetime) -> datetime:
    normalized = ensure_utc(value)
    return normalized.astimezone(IST) if normalized else utc_now().astimezone(IST)


def is_market_open(value: datetime | None = None) -> bool:
    value = value or utc_now()
    local = to_ist(value)
    if local.weekday() >= 5:
        return False
    open_time = time(9, 15)
    close_time = time(15, 30)
    return open_time <= local.time() <= close_time
