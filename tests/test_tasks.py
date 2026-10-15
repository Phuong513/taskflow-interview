"""Independent task CRUD, search, filtering, and comment tests."""

from datetime import datetime

import pytest

from app.models import Comment, Task


def test_create_task(client, auth_headers, test_user, db_session):
    payload = {"title": "Test Task", "priority": 2, "status": "todo"}
    response = client.post("/tasks/", json=payload, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert {key: data[key] for key in payload} == payload
    assert data["owner_id"] == test_user["id"]
    assert data["description"] is None
    assert data["due_date"] is None
    assert data["tags"] is None
    assert data["comments"] == []
    assert datetime.fromisoformat(data["created_at"])
    stored = db_session.get(Task, data["id"])
    assert stored is not None
    assert stored.title == payload["title"]
    assert stored.owner_id == test_user["id"]


def test_list_tasks(client, auth_headers, task):
    response = client.get("/tasks/", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [task]


def test_list_tasks_empty(client, auth_headers):
    response = client.get("/tasks/", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_get_task(client, auth_headers, task):
    response = client.get(f"/tasks/{task['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == task


def test_update_task(client, auth_headers, task, db_session):
    response = client.put(
        f"/tasks/{task['id']}", json={"status": "in_progress"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == {**task, "status": "in_progress"}
    assert db_session.get(Task, task["id"]).status == "in_progress"
    persisted = client.get(f"/tasks/{task['id']}", headers=auth_headers)
    assert persisted.status_code == 200
    assert persisted.json() == response.json()


def test_delete_task(client, auth_headers, task, db_session):
    response = client.delete(f"/tasks/{task['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"message": "Task deleted"}
    assert db_session.get(Task, task["id"]) is None


def test_get_deleted_task(client, auth_headers, task):
    deleted = client.delete(f"/tasks/{task['id']}", headers=auth_headers)
    assert deleted.status_code == 200
    response = client.get(f"/tasks/{task['id']}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_task(client, auth_headers, method):
    kwargs = {"json": {"title": "Updated"}} if method == "put" else {}
    response = client.request(method, "/tasks/999", headers=auth_headers, **kwargs)

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


@pytest.mark.parametrize("method", ["get", "post", "put", "delete"])
def test_tasks_require_authentication(client, task, db_session, method):
    path = "/tasks/" if method in {"get", "post"} else f"/tasks/{task['id']}"
    kwargs = (
        {"json": {"title": "Unauthorized change"}}
        if method in {"post", "put"}
        else {}
    )
    response = client.request(method, path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert db_session.query(Task).count() == 1
    assert db_session.get(Task, task["id"]).title == task["title"]


def test_create_task_missing_title(client, auth_headers, db_session):
    response = client.post("/tasks/", json={"priority": 2}, headers=auth_headers)

    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", "title"] and error["type"] == "missing"
        for error in response.json()["detail"]
    )
    assert db_session.query(Task).count() == 0


def test_search_tasks(client, auth_headers, task_factory):
    matching = task_factory(title="Write API documentation")
    task_factory(title="Configure deployment")
    response = client.get("/tasks/search", params={"q": "API"}, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == matching["id"]
    assert data[0]["title"] == matching["title"]
    assert data[0]["owner_id"] == matching["owner_id"]


def test_search_tasks_no_matches(client, auth_headers, task):
    response = client.get(
        "/tasks/search", params={"q": "not-present"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == []


def test_filter_tasks_by_status(client, auth_headers, task_factory):
    matching = task_factory(status="done")
    task_factory(status="todo")
    response = client.get("/tasks/", params={"status": "done"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [matching]


def test_add_and_retrieve_comment(client, auth_headers, task, test_user, db_session):
    response = client.post(
        f"/tasks/{task['id']}/comments",
        json={"content": "Ready for review"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    comment = response.json()
    assert comment["content"] == "Ready for review"
    assert comment["author_id"] == test_user["id"]
    assert datetime.fromisoformat(comment["created_at"])
    stored = db_session.get(Comment, comment["id"])
    assert stored.task_id == task["id"]
    assert stored.content == comment["content"]
    retrieved = client.get(f"/tasks/{task['id']}", headers=auth_headers)
    assert retrieved.status_code == 200
    assert retrieved.json()["comments"] == [comment]


def test_comment_on_missing_task(client, auth_headers, db_session):
    response = client.post(
        "/tasks/999/comments", json={"content": "Hello"}, headers=auth_headers
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}
    assert db_session.query(Comment).count() == 0


def test_task_summary_by_user(client, auth_headers, test_user, task_factory, user_factory):
    empty_user = user_factory()
    task_factory(status="todo", priority=2)
    task_factory(status="in_progress", priority=2)
    task_factory(status="done", priority=3)
    response = client.get("/tasks/summary/by-user", headers=auth_headers)

    assert response.status_code == 200
    by_user = {row["user_id"]: row for row in response.json()}
    assert by_user == {
        test_user["id"]: {
            "user_id": test_user["id"],
            "username": test_user["username"],
            "task_count": 3,
            "avg_priority_score": 16.67,
        },
        empty_user["id"]: {
            "user_id": empty_user["id"],
            "username": empty_user["username"],
            "task_count": 0,
            "avg_priority_score": 0,
        },
    }
