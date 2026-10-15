"""User retrieval and persistence checks without cross-test state."""

from passlib.hash import bcrypt

from app.models import User


def test_get_me(client, auth_headers, test_user):
    response = client.get("/users/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == test_user
    assert "password_hash" not in response.json()
    assert "password" not in response.json()


def test_list_users_authenticated(client, auth_headers, test_user, user_factory):
    other_user = user_factory()
    response = client.get("/users/", headers=auth_headers)

    assert response.status_code == 200
    for user in response.json():
        assert "password_hash" not in user
        assert "password" not in user
    assert sorted(response.json(), key=lambda user: user["id"]) == sorted(
        [test_user, other_user], key=lambda user: user["id"]
    )


def test_list_users_unauthenticated(client):
    response = client.get("/users/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_update_user(client, auth_headers, test_user, db_session):
    payload = {"username": "updateduser", "email": "updated@example.com"}
    response = client.put(
        f"/users/{test_user['id']}", json=payload, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == {**test_user, **payload}
    assert "password_hash" not in response.json()
    assert "password" not in response.json()
    stored = db_session.get(User, test_user["id"])
    assert stored.username == payload["username"]
    assert stored.email == payload["email"]


def test_get_user(client, auth_headers, test_user):
    response = client.get(f"/users/{test_user['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == test_user
    assert "password_hash" not in response.json()
    assert "password" not in response.json()


def test_update_password_keeps_credentials_private(
    client, auth_headers, test_user, db_session
):
    original_hash = db_session.get(User, test_user["id"]).password_hash
    new_password = "Updated-password-456!"
    response = client.put(
        f"/users/{test_user['id']}",
        json={"password": new_password},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == test_user
    assert "password_hash" not in response.json()
    assert "password" not in response.json()
    db_session.expire_all()
    stored = db_session.get(User, test_user["id"])
    assert stored.password_hash
    assert stored.password_hash != original_hash
    assert stored.password_hash != new_password
    assert bcrypt.identify(stored.password_hash)
    assert bcrypt.verify(new_password, stored.password_hash)
    login = client.post(
        "/auth/login",
        data={"username": test_user["username"], "password": new_password},
    )
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"


def test_get_missing_user(client, auth_headers):
    response = client.get("/users/999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_get_user_tasks(client, auth_headers, test_user, task, user_factory):
    other_user = user_factory()
    response = client.get(f"/users/{test_user['id']}/tasks", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [task]
    empty = client.get(f"/users/{other_user['id']}/tasks", headers=auth_headers)
    assert empty.status_code == 200
    assert empty.json() == []
