from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.core.config import get_settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import create_session_token
from app.db.session import get_db
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest, UserResponse
from app.services.auth_service import authenticate_user, create_single_user, has_user


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_response(user, authenticated: bool, db: Session) -> AuthResponse:
    user_exists = has_user(db)
    return AuthResponse(
        authenticated=authenticated,
        user=(
            UserResponse(username=user.admin_username, timezone=user.timezone)
            if user
            else None
        ),
        has_user=user_exists,
        signup_allowed=not user_exists,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    settings = get_settings()
    key = request.client.host if request.client else "unknown"
    if not login_rate_limiter.allow(
        key,
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_session_token(user.admin_username)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
    )
    return _auth_response(user, authenticated=True, db=db)


@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    existing_user = has_user(db)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Single-user account already exists")

    user = create_single_user(
        db,
        username=payload.username,
        password=payload.password,
        timezone=payload.timezone,
    )
    settings = get_settings()
    token = create_session_token(user.admin_username)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
    )
    return _auth_response(user, authenticated=True, db=db)


@router.post("/logout", response_model=AuthResponse)
def logout(response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name)
    return _auth_response(None, authenticated=False, db=db)


@router.get("/me", response_model=AuthResponse)
def me(user=Depends(get_optional_user), db: Session = Depends(get_db)) -> AuthResponse:
    return _auth_response(user, authenticated=bool(user), db=db)
