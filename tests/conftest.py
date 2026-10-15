"""Function-scoped fixtures with a disposable database for every test."""

from itertools import count
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Bootstrap before app imports; never use developer secrets or a disk database.
os.environ.update({
    "SECRET_KEY": "taskflow-test-key-for-isolated-tests-only",
    "DATABASE_URL": "sqlite://",
    "APP_NAME": "TaskFlow",
    "APP_VERSION": "1.0.0",
    "TASKFLOW_DEBUG": "false",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
    "DEFAULT_PAGE_SIZE": "10",
    "MAX_PAGE_SIZE": "100",
})

from app import database
from app.main import app


@pytest.fixture
def db_engine():
    # Share this test's in-memory database with TestClient's request thread.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        database.Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def client(db_engine, monkeypatch):
    def override_get_db():
        with Session(db_engine) as session:
            yield session

    # Redirect startup's init_db() as well as request sessions.
    monkeypatch.setattr(database, "engine", db_engine)
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[database.get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.fixture
def user_data():
    return {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "Test-password-123!",
    }


@pytest.fixture
def user_factory(client):
    sequence = count(1)

    def create_user(**overrides):
        number = next(sequence)
        payload = {
            "username": f"user{number}",
            "email": f"user{number}@example.com",
            "password": "Test-password-123!",
            **overrides,
        }
        response = client.post("/auth/register", json=payload)
        assert response.status_code == 200, response.text
        return response.json()

    return create_user


@pytest.fixture
def test_user(user_factory, user_data):
    return user_factory(**user_data)


@pytest.fixture
def test_user_token(client, test_user, user_data):
    response = client.post(
        "/auth/login",
        data={"username": test_user["username"], "password": user_data["password"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["token_type"] == "bearer"
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(test_user_token):
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def task_factory(client, auth_headers):
    def create_task(**overrides):
        payload = {"title": "Test Task", "priority": 2, "status": "todo", **overrides}
        response = client.post("/tasks/", json=payload, headers=auth_headers)
        assert response.status_code == 200, response.text
        return response.json()

    return create_task


@pytest.fixture
def task(task_factory):
    return task_factory()
