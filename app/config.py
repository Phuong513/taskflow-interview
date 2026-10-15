"""Validated environment configuration shared by the application."""

from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    APP_NAME: str = "TaskFlow"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, validation_alias="TASKFLOW_DEBUG")
    DATABASE_URL: SecretStr
    SECRET_KEY: SecretStr
    ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)
    DEFAULT_PAGE_SIZE: int = Field(default=10, gt=0)
    MAX_PAGE_SIZE: int = Field(default=100, gt=0)

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().strip()) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 non-padding characters")
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL") from None
        return value


try:
    settings = Settings()
except ValidationError as error:
    fields = ", ".join(sorted({
        str(issue["loc"][0])
        for issue in error.errors(include_input=False, include_context=False)
    }))
    raise RuntimeError(
        f"Invalid application configuration: {fields}. "
        "Set the required environment values or configure .env using .env.example."
    ) from None

# Preserve the public constants used by the routers and database module.
APP_NAME = settings.APP_NAME
APP_VERSION = settings.APP_VERSION
DEBUG = settings.DEBUG
DATABASE_URL = settings.DATABASE_URL.get_secret_value()
SECRET_KEY = settings.SECRET_KEY.get_secret_value()
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
DEFAULT_PAGE_SIZE = settings.DEFAULT_PAGE_SIZE
MAX_PAGE_SIZE = settings.MAX_PAGE_SIZE

PRIORITY_LOW = 1
PRIORITY_MEDIUM = 2
PRIORITY_HIGH = 3
VALID_PRIORITIES = [PRIORITY_LOW, PRIORITY_MEDIUM, PRIORITY_HIGH]
VALID_STATUSES = ["todo", "in_progress", "done"]
