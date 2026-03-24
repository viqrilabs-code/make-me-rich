from __future__ import annotations

import hashlib
import uuid


def generate_client_order_id(prefix: str = "ord") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def generate_idempotency_key(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

