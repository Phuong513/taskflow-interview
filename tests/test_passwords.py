"""Password storage, verification, and migration through the auth boundary."""

import hashlib

import pytest
from passlib.hash import bcrypt, bcrypt_sha256
from sqlalchemy.orm import Session

from app.routers import auth
from app.models import User
from app.routers.auth import hash_password, verify_password


def test_password_hashes_are_salted():
    password = "Test-password-123!"
    first = hash_password(password)
    second = hash_password(password)

    assert bcrypt.identify(first)
    assert bcrypt.identify(second)
    assert first != second
    assert password not in first
    assert bcrypt.verify(password, first)
    assert verify_password(password, first)
    assert not verify_password("Wrong-password-123!", first)


def test_registration_stores_bcrypt(client, user_data, db_session):
    response = client.post("/auth/register", json=user_data)

    assert response.status_code == 200
    stored = db_session.get(User, response.json()["id"])
    assert bcrypt.identify(stored.password_hash)
    assert bcrypt.verify(user_data["password"], stored.password_hash)
    assert "password_hash" not in response.json()


@pytest.mark.parametrize(
    "password", ["Legacy-password-123!", "x" * 73, "old\x00password"]
)
def test_successful_legacy_login_upgrades_hash(client, db_session, password):
    legacy_hash = hashlib.md5(password.encode()).hexdigest()
    user = User(username="legacy", email="legacy@example.com", password_hash=legacy_hash)
    db_session.add(user)
    db_session.commit()
    user_id = user.id

    response = client.post(
        "/auth/login", data={"username": "legacy", "password": password}
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    db_session.expire_all()
    upgraded = db_session.get(User, user_id).password_hash
    assert upgraded != legacy_hash
    assert bcrypt.identify(upgraded) or bcrypt_sha256.identify(upgraded)
    assert verify_password(password, upgraded)
    again = client.post(
        "/auth/login", data={"username": "legacy", "password": password}
    )
    assert again.status_code == 200
    db_session.expire_all()
    assert db_session.get(User, user_id).password_hash == upgraded


def test_failed_legacy_login_does_not_change_hash(client, db_session):
    legacy_hash = hashlib.md5(b"Legacy-password-123!").hexdigest()
    user = User(username="legacy", email="legacy@example.com", password_hash=legacy_hash)
    db_session.add(user)
    db_session.commit()
    user_id = user.id

    response = client.post(
        "/auth/login", data={"username": "legacy", "password": "Wrong-password-123!"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}
    db_session.expire_all()
    assert db_session.get(User, user_id).password_hash == legacy_hash


@pytest.mark.parametrize("stored_hash", [None, "", "not-a-hash", "$2b$12$broken"])
def test_login_with_invalid_stored_hash_fails_closed(client, db_session, stored_hash):
    db_session.add(
        User(username="broken", email="broken@example.com", password_hash=stored_hash)
    )
    db_session.commit()

    response = client.post(
        "/auth/login", data={"username": "broken", "password": "Test-password-123!"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}


@pytest.mark.parametrize(
    "password", ["x" * 73, "\u00e9" * 37, "new\x00password", "x" * 4096],
    ids=["over-72-bytes", "multibyte", "nul", "max-length"],
)
def test_extended_password_registration_and_login(
    client, user_data, db_session, password
):
    response = client.post("/auth/register", json={**user_data, "password": password})

    assert response.status_code == 200
    stored_hash = db_session.get(User, response.json()["id"]).password_hash
    assert bcrypt_sha256.identify(stored_hash)
    assert verify_password(password, stored_hash)
    assert not verify_password(password + "different", stored_hash)
    login = client.post(
        "/auth/login", data={"username": user_data["username"], "password": password}
    )
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"


@pytest.mark.parametrize("suffix", ["x", "\x00suffix", "\u00e9"])
def test_bcrypt_does_not_accept_truncated_password_alias(suffix):
    password = "x" * 72
    stored_hash = hash_password(password)

    assert bcrypt.identify(stored_hash)
    assert verify_password(password, stored_hash)
    assert not verify_password(password + suffix, stored_hash)


@pytest.mark.parametrize("method", ["register", "update"])
def test_oversized_password_is_rejected(
    client, user_data, auth_headers, test_user, method
):
    password = "x" * 4097
    if method == "register":
        response = client.post(
            "/auth/register",
            json={
                **user_data,
                "username": "oversized",
                "email": "oversized@example.com",
                "password": password,
            },
        )
    else:
        response = client.put(
            f"/users/{test_user['id']}", json={"password": password}, headers=auth_headers
        )

    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", "password"] for error in response.json()["detail"]
    )


def test_oversized_login_fails_closed(client, test_user):
    response = client.post(
        "/auth/login",
        data={"username": test_user["username"], "password": "x" * 4097},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}


def test_oversized_legacy_password_requires_reset(client, db_session):
    password = "x" * 4097
    legacy_hash = hashlib.md5(password.encode()).hexdigest()
    user = User(username="legacy", email="legacy@example.com", password_hash=legacy_hash)
    db_session.add(user)
    db_session.commit()
    user_id = user.id

    response = client.post(
        "/auth/login", data={"username": "legacy", "password": password}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}
    db_session.expire_all()
    assert db_session.get(User, user_id).password_hash == legacy_hash


@pytest.mark.parametrize("concurrent_password", ["New-password-456!", "Legacy-password-123!"])
def test_migration_preserves_concurrent_password_change(
    client, db_session, db_engine, monkeypatch, concurrent_password
):
    old_password = "Legacy-password-123!"
    user = User(
        username="legacy",
        email="legacy@example.com",
        password_hash=hashlib.md5(old_password.encode()).hexdigest(),
    )
    db_session.add(user)
    db_session.commit()
    user_id = user.id
    concurrent_hash = hash_password(concurrent_password)

    def hash_during_password_change(password):
        # Interleave a committed password change after login's verification.
        with Session(db_engine) as other_session:
            other_user = other_session.get(User, user_id)
            other_user.password_hash = concurrent_hash
            other_session.commit()
        return hash_password(password)

    monkeypatch.setattr(auth, "hash_password", hash_during_password_change)
    response = client.post(
        "/auth/login", data={"username": "legacy", "password": old_password}
    )

    expected_status = 200 if concurrent_password == old_password else 401
    assert response.status_code == expected_status
    db_session.expire_all()
    assert db_session.get(User, user_id).password_hash == concurrent_hash
    assert verify_password(concurrent_password, concurrent_hash)
    if expected_status == 401:
        assert response.json() == {"detail": "Incorrect username or password"}
        assert not verify_password(old_password, concurrent_hash)


def test_current_bcrypt_login_does_not_rehash(client, test_user, user_data, db_session):
    original = db_session.get(User, test_user["id"]).password_hash
    assert bcrypt.identify(original)

    response = client.post(
        "/auth/login",
        data={"username": test_user["username"], "password": user_data["password"]},
    )

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(User, test_user["id"]).password_hash == original
