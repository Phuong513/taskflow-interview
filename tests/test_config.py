"""Environment loading, startup validation, and secret redaction."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture
def clean_settings_env(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field, raising=False)
        alias = Settings.model_fields[field].validation_alias
        if isinstance(alias, str):
            monkeypatch.delenv(alias, raising=False)


def test_settings_load_from_environment(monkeypatch, clean_settings_env):
    monkeypatch.setenv("SECRET_KEY", "environment-secret-key-with-at-least-32-characters")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///environment.db")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "45")

    settings = Settings(_env_file=None)

    assert settings.SECRET_KEY.get_secret_value().startswith("environment-secret")
    assert settings.DATABASE_URL.get_secret_value() == "sqlite:///environment.db"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 45
    assert settings.DEBUG is False
    assert "environment-secret" not in repr(settings)
    assert "environment.db" not in repr(settings)


def test_dotenv_loads_and_environment_takes_precedence(
    tmp_path, monkeypatch, clean_settings_env
):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "SECRET_KEY=dotenv-secret-key-with-at-least-32-characters\n"
        "DATABASE_URL=sqlite:///dotenv.db\n"
        "ACCESS_TOKEN_EXPIRE_MINUTES=60\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite:///override.db")

    settings = Settings(_env_file=dotenv)

    assert settings.SECRET_KEY.get_secret_value().startswith("dotenv-secret")
    assert settings.DATABASE_URL.get_secret_value() == "sqlite:///override.db"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 60


def test_debug_setting_uses_application_namespace(monkeypatch, clean_settings_env):
    monkeypatch.setenv("DEBUG", "release")
    values = {
        "SECRET_KEY": "test-secret-key-with-at-least-32-characters",
        "DATABASE_URL": "sqlite://",
    }
    assert Settings(_env_file=None, **values).DEBUG is False
    monkeypatch.setenv("TASKFLOW_DEBUG", "true")
    assert Settings(_env_file=None, **values).DEBUG is True


@pytest.mark.parametrize("missing_field", ["SECRET_KEY", "DATABASE_URL"])
def test_sensitive_settings_are_required(clean_settings_env, missing_field):
    values = {
        "SECRET_KEY": "test-secret-key-with-at-least-32-characters",
        "DATABASE_URL": "sqlite://",
    }
    values.pop(missing_field)

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, **values)

    assert any(
        issue["loc"] == (missing_field,) and issue["type"] == "missing"
        for issue in caught.value.errors()
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("SECRET_KEY", "weak-secret"),
        ("SECRET_KEY", " " * 40),
        ("DATABASE_URL", "not-a-database-url"),
        ("DATABASE_URL", ""),
        ("ACCESS_TOKEN_EXPIRE_MINUTES", "0"),
        ("ALGORITHM", "none"),
    ],
)
def test_invalid_settings_are_rejected(clean_settings_env, field, value):
    values = {
        "SECRET_KEY": "test-secret-key-with-at-least-32-characters",
        "DATABASE_URL": "sqlite://",
        field: value,
    }

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, **values)

    assert any(issue["loc"] == (field,) for issue in caught.value.errors())
    assert "weak-secret" not in str(caught.value)


def subprocess_env(values):
    fields = set(Settings.model_fields)
    fields.update(
        field.validation_alias for field in Settings.model_fields.values()
        if isinstance(field.validation_alias, str)
    )
    env = {key: value for key, value in os.environ.items() if key.upper() not in fields}
    env.update(values)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return env


def test_missing_configuration_fails_startup_clearly(tmp_path):
    result = subprocess.run(
        [sys.executable, "-B", "-c", "import app.main"],
        cwd=tmp_path,
        env=subprocess_env({}),
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "Invalid application configuration" in result.stderr
    assert "SECRET_KEY" in result.stderr
    assert "DATABASE_URL" in result.stderr
    assert ".env.example" in result.stderr


def test_startup_error_does_not_expose_credentials(tmp_path):
    result = subprocess.run(
        [sys.executable, "-B", "-c", "import app.main"],
        cwd=tmp_path,
        env=subprocess_env({
            "SECRET_KEY": "private-weak-key",
            "DATABASE_URL": "postgresql://user:private-database-password@localhost/tasks",
        }),
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr
    assert "private-weak-key" not in result.stderr
    assert "private-database-password" not in result.stderr


def test_application_starts_with_dotenv(tmp_path):
    (tmp_path / ".env").write_text(
        "SECRET_KEY=dotenv-startup-secret-key-with-at-least-32-characters\n"
        "DATABASE_URL=sqlite://\n",
        encoding="utf-8",
    )
    script = (
        "from fastapi.testclient import TestClient; from app.main import app; "
        "client = TestClient(app); "
        "client.__enter__(); response = client.get('/health'); "
        "assert response.status_code == 200; "
        "assert response.json()['status'] == 'ok'; client.__exit__(None, None, None)"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=tmp_path,
        env=subprocess_env({}),
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
