from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import SessionLocal
from app.scheduler.engine import scheduler_manager


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc)}


@router.get("/ready")
def ready() -> dict:
    db_ok = False
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
        db_ok = True
    return {
        "status": "ready" if db_ok and scheduler_manager.started else "degraded",
        "database": db_ok,
        "scheduler": scheduler_manager.started,
        "timestamp": datetime.now(timezone.utc),
    }

