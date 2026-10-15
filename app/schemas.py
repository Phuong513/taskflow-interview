# app/schemas.py

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── Auth ────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# ── User ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: str
    password: str = Field(max_length=4096)
    # Issue: no minimum length, email format check, or password strength rules


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = Field(default=None, max_length=4096)


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserSummary(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True


# ── Comment ───────────────────────────────────────────────────────────────────

class CommentCreate(BaseModel):
    content: str


class CommentOut(BaseModel):
    id: int
    content: str
    author_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Task ──────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: Optional[str] = "todo"
    priority: Optional[int] = 2
    due_date: Optional[datetime] = None
    tags: Optional[str] = None
    # Issue: no validation that status is one of the valid values
    # Issue: no validation that priority is 1, 2, or 3


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[datetime] = None
    tags: Optional[str] = None


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    priority: int
    owner_id: Optional[int]
    created_at: datetime
    due_date: Optional[datetime]
    tags: Optional[str]
    comments: List[CommentOut] = []

    class Config:
        from_attributes = True
