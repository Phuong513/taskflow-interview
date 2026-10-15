"""Independent registration, login, and token validation tests."""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.config import ALGORITHM, SECRET_KEY
from app.models import User


def test_register(client, user_data, db_session):
    response = client.post("/auth/register", json=user_data)

    assert response.status_code == 200
    data = response.json()
    assert "password_hash" not in data
    assert "password" not in data
    assert data["username"] == user_data["username"]
    assert data["email"] == user_data["email"]
    assert data["role"] == "member"
    assert data["is_active"] is True
    assert datetime.fromisoformat(data["created_at"])
    stored = db_session.get(User, data["id"])
    assert stored is not None
    assert stored.username == user_data["username"]
    assert stored.email == user_data["email"]
    assert stored.password_hash


def test_register_duplicate_email(client, test_user, user_data, db_session):
    response = client.post(
        "/auth/register", json={**user_data, "username": "anotheruser"}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Email already registered"}
    assert db_session.query(User).count() == 1


def test_login_success(client, test_user, user_data):
    before_login = datetime.now(timezone.utc)
    response = client.post(
        "/auth/login",
        data={"username": user_data["username"], "password": user_data["password"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    claims = jwt.decode(data["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    assert claims["sub"] == str(test_user["id"])
    assert isinstance(claims["ver"], str)
    assert claims["exp"] > before_login.timestamp()
    me = client.get(
        "/users/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["id"] == test_user["id"]


def test_login_wrong_password(client, test_user):
    response = client.post(
        "/auth/login",
        data={"username": test_user["username"], "password": "Wrong-password-123!"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}
    assert "access_token" not in response.json()


def test_login_unknown_user(client):
    response = client.post(
        "/auth/login", data={"username": "missing", "password": "Wrong-password-123!"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}


@pytest.mark.parametrize("missing_field", ["username", "email", "password"])
def test_register_missing_required_field(client, user_data, db_session, missing_field):
    payload = {key: value for key, value in user_data.items() if key != missing_field}
    response = client.post("/auth/register", json=payload)

    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", missing_field] and error["type"] == "missing"
        for error in response.json()["detail"]
    )
    assert db_session.query(User).count() == 0


@pytest.mark.parametrize("token_kind", ["expired", "invalid_signature", "malformed"])
def test_reject_invalid_token(client, test_user, token_kind):
    claims = {
        "sub": test_user["username"],
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    if token_kind == "expired":
        claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=5)
    signing_key = (
        "a-different-test-signing-key"
        if token_kind == "invalid_signature"
        else SECRET_KEY
    )
    token = (
        "invalid-token"
        if token_kind == "malformed"
        else jwt.encode(claims, signing_key, algorithm=ALGORITHM)
    )
    response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"
