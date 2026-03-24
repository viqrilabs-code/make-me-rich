from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_session_token
from app.db.session import get_db
from app.models import UserConfig


settings = get_settings()


def get_optional_user(
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db: Session = Depends(get_db),
) -> UserConfig | None:
    if not session_token:
        return None
    username = decode_session_token(session_token)
    if not username:
        return None
    return db.scalar(select(UserConfig).where(UserConfig.admin_username == username))


def get_current_user(user: UserConfig | None = Depends(get_optional_user)) -> UserConfig:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user
