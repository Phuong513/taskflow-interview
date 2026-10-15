"""Ownership, administrator privileges, and deletion lifecycle regressions."""

import pytest

from app.models import Comment, Task, User


@pytest.fixture
def identity_factory(client, user_factory, db_session):
    def create_identity(role="member"):
        user = user_factory()
        if role != "member":
            stored = db_session.get(User, user["id"])
            stored.role = role
            db_session.commit()
        response = client.post(
            "/auth/login",
            data={"username": user["username"], "password": "Test-password-123!"},
        )
        assert response.status_code == 200, response.text
        return user, {"Authorization": f"Bearer {response.json()['access_token']}"}

    return create_identity


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize("actor", ["owner", "other_member", "admin"])
def test_task_mutation_permissions(
    client, task, auth_headers, identity_factory, db_session, method, actor
):
    headers = auth_headers
    if actor != "owner":
        _, headers = identity_factory(role="admin" if actor == "admin" else "member")
    kwargs = {"json": {"title": "Authorized change"}} if method == "put" else {}
    response = client.request(method, f"/tasks/{task['id']}", headers=headers, **kwargs)

    allowed = actor in {"owner", "admin"}
    assert response.status_code == (200 if allowed else 403)
    db_session.expire_all()
    stored = db_session.get(Task, task["id"])
    if not allowed:
        assert response.json() == {"detail": "Not authorized"}
        assert stored.title == task["title"]
        assert stored.owner_id == task["owner_id"]
    elif method == "put":
        assert response.json()["title"] == "Authorized change"
        assert stored.title == "Authorized change"
        assert stored.owner_id == task["owner_id"]
    else:
        assert response.json() == {"message": "Task deleted"}
        assert stored is None


@pytest.mark.parametrize("actor", ["self", "other_member", "admin"])
@pytest.mark.parametrize("method", ["put", "delete"])
def test_user_mutation_permissions(
    client, auth_headers, test_user, identity_factory, db_session, actor, method
):
    headers = auth_headers
    if actor != "self":
        _, headers = identity_factory(role="admin" if actor == "admin" else "member")
    kwargs = {"json": {"email": "changed@example.com"}} if method == "put" else {}
    response = client.request(method, f"/users/{test_user['id']}", headers=headers, **kwargs)

    allowed = actor in {"self", "admin"}
    assert response.status_code == (200 if allowed else 403)
    db_session.expire_all()
    stored = db_session.get(User, test_user["id"])
    if not allowed:
        assert response.json() == {"detail": "Not authorized"}
        assert stored.email == test_user["email"]
    elif method == "put":
        assert response.json()["email"] == "changed@example.com"
        assert stored.email == "changed@example.com"
    else:
        assert response.json() == {"message": "User deleted"}
        assert stored is None


def test_magic_header_cannot_delete_another_user(
    client, auth_headers, user_factory, db_session
):
    target = user_factory()
    response = client.delete(
        f"/users/{target['id']}",
        headers={**auth_headers, "X-Admin-Override": "admin-secret-2024"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}
    assert db_session.get(User, target["id"]) is not None


def test_member_cannot_take_over_another_account(
    client, auth_headers, user_factory, db_session
):
    target = user_factory()
    original_hash = db_session.get(User, target["id"]).password_hash
    response = client.put(
        f"/users/{target['id']}",
        json={"password": "Attacker-password-123!"},
        headers=auth_headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}
    db_session.expire_all()
    assert db_session.get(User, target["id"]).password_hash == original_hash
    login = client.post(
        "/auth/login",
        data={"username": target["username"], "password": "Attacker-password-123!"},
    )
    assert login.status_code == 401


@pytest.mark.parametrize("method", ["put", "delete"])
def test_deleted_owner_leaves_readable_records_with_admin_only_mutation(
    client, task, auth_headers, test_user, identity_factory, db_session, method
):
    comment = client.post(
        f"/tasks/{task['id']}/comments", json={"content": "Retain me"}, headers=auth_headers
    )
    assert comment.status_code == 200
    _, admin_headers = identity_factory(role="admin")
    _, member_headers = identity_factory()
    deleted = client.delete(f"/users/{test_user['id']}", headers=admin_headers)
    assert deleted.status_code == 200

    listed = client.get("/tasks/", headers=member_headers)
    assert listed.status_code == 200
    retained = next(item for item in listed.json() if item["id"] == task["id"])
    assert retained["owner_id"] is None
    assert retained["comments"][0]["author_id"] is None
    assert retained["comments"][0]["content"] == "Retain me"
    assert db_session.get(Comment, comment.json()["id"]) is not None
    kwargs = {"json": {"title": "Admin change"}} if method == "put" else {}
    denied = client.request(
        method, f"/tasks/{task['id']}", headers=member_headers, **kwargs
    )
    assert denied.status_code == 403
    allowed = client.request(
        method, f"/tasks/{task['id']}", headers=admin_headers, **kwargs
    )
    assert allowed.status_code == 200


@pytest.mark.parametrize("method", ["put", "delete"])
def test_user_mutations_require_authentication(client, test_user, method):
    kwargs = {"json": {"email": "changed@example.com"}} if method == "put" else {}
    response = client.request(method, f"/users/{test_user['id']}", **kwargs)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize("method", ["put", "delete"])
def test_revoked_admin_role_cannot_mutate_another_users_task(
    client, task, identity_factory, db_session, method
):
    admin, headers = identity_factory(role="admin")
    db_session.get(User, admin["id"]).role = "member"
    db_session.commit()
    kwargs = {"json": {"title": "Forbidden"}} if method == "put" else {}

    response = client.request(method, f"/tasks/{task['id']}", headers=headers, **kwargs)

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}
    db_session.expire_all()
    assert db_session.get(Task, task["id"]).title == task["title"]


def test_released_username_does_not_rebind_token(
    client, auth_headers, test_user, user_factory, db_session
):
    renamed = client.put(
        f"/users/{test_user['id']}", json={"username": "renamed"}, headers=auth_headers
    )
    assert renamed.status_code == 200
    victim = user_factory(username=test_user["username"], email="victim@example.com")

    me = client.get("/users/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["id"] == test_user["id"]
    assert me.json()["username"] == "renamed"
    denied = client.put(
        f"/users/{victim['id']}",
        json={"password": "Attacker-password-123!"},
        headers=auth_headers,
    )
    assert denied.status_code == 403
    assert db_session.get(User, victim["id"]).username == test_user["username"]


def test_password_change_revokes_existing_token(client, auth_headers, test_user):
    response = client.put(
        f"/users/{test_user['id']}",
        json={"password": "Replacement-password-123!"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    rejected = client.get("/users/me", headers=auth_headers)
    assert rejected.status_code == 401
    assert rejected.json() == {"detail": "Could not validate credentials"}
    login = client.post(
        "/auth/login",
        data={"username": test_user["username"], "password": "Replacement-password-123!"},
    )
    assert login.status_code == 200


def test_deleted_user_token_cannot_authenticate_reused_id(
    client, auth_headers, test_user, user_factory
):
    deleted = client.delete(f"/users/{test_user['id']}", headers=auth_headers)
    assert deleted.status_code == 200
    replacement = user_factory()
    # SQLite may reuse the deleted highest integer ID; credentials still differ.
    assert replacement["id"] == test_user["id"]

    response = client.get("/users/me", headers=auth_headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
