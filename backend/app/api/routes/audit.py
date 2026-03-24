from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AuditLog, RiskEvent, SchedulerRun


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
def audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "timestamp": row.timestamp,
            "category": row.category,
            "message": row.message,
            "metadata_json": row.metadata_json,
        }
        for row in rows
    ]


@router.get("/risk-events")
def risk_events(
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(select(RiskEvent).order_by(RiskEvent.timestamp.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "timestamp": row.timestamp,
            "event_type": row.event_type,
            "severity": row.severity,
            "message": row.message,
            "metadata_json": row.metadata_json,
        }
        for row in rows
    ]


@router.get("/scheduler-runs")
def scheduler_runs(
    limit: int = Query(default=50, ge=1, le=200),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(select(SchedulerRun).order_by(SchedulerRun.started_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "status": row.status,
            "lock_acquired": row.lock_acquired,
            "actions_taken_json": row.actions_taken_json,
            "error_message": row.error_message,
        }
        for row in rows
    ]

