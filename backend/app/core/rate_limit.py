from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone


class LoginRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)
        bucket = self._attempts[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


login_rate_limiter = LoginRateLimiter()

