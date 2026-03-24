from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.hash import bcrypt, pbkdf2_sha256

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$pbkdf2-sha256$"):
        return pbkdf2_sha256.verify(password, password_hash)
    if password_hash.startswith("$2"):
        return bcrypt.verify(password, password_hash)
    return False


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt="session")


def create_session_token(username: str) -> str:
    return _serializer().dumps({"username": username})


def decode_session_token(token: str) -> str | None:
    settings = get_settings()
    try:
        payload = _serializer().loads(token, max_age=settings.session_ttl_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None
    return payload.get("username")
