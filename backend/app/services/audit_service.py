from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AuditLog, RiskEvent


def add_audit_log(db: Session, category: str, message: str, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            timestamp=datetime.now(timezone.utc),
            category=category,
            message=message,
            metadata_json=metadata or {},
        )
    )


def add_risk_event(
    db: Session,
    event_type: str,
    severity: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    db.add(
        RiskEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            severity=severity,
            message=message,
            metadata_json=metadata or {},
        )
    )

