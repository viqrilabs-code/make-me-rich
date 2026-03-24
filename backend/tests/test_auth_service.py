from __future__ import annotations

import pytest

from app.services.auth_service import authenticate_user, create_single_user, has_user


def test_create_single_user_and_authenticate(db_session) -> None:
    assert has_user(db_session) is False

    user = create_single_user(
        db_session,
        username="trader",
        password="super-secret-pass",
        timezone="Asia/Kolkata",
    )

    assert user.admin_username == "trader"
    assert has_user(db_session) is True
    assert authenticate_user(db_session, "trader", "super-secret-pass") is not None


def test_create_single_user_rejects_second_account(db_session) -> None:
    create_single_user(
        db_session,
        username="trader",
        password="super-secret-pass",
        timezone="Asia/Kolkata",
    )

    with pytest.raises(ValueError, match="already exists"):
        create_single_user(
            db_session,
            username="another",
            password="another-secret",
            timezone="Asia/Kolkata",
        )
