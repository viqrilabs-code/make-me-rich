from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import UserConfig


def get_single_user(db: Session) -> UserConfig | None:
    return db.scalar(select(UserConfig).limit(1))


def has_user(db: Session) -> bool:
    return get_single_user(db) is not None


def create_single_user(db: Session, username: str, password: str, timezone: str) -> UserConfig:
    existing = get_single_user(db)
    if existing:
        raise ValueError("A user already exists for this app.")

    user = UserConfig(
        admin_username=username.strip(),
        password_hash=hash_password(password),
        timezone=timezone.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> UserConfig | None:
    user = get_single_user(db)
    if not user:
        return None
    if user.admin_username != username:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
