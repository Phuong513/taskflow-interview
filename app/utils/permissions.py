"""Shared authorization for records owned by a user."""

from typing import Optional

from fastapi import HTTPException

from app.models import User


def require_owner_or_admin(current_user: User, owner_id: Optional[int]) -> None:
    if current_user.role != "admin" and current_user.id != owner_id:
        raise HTTPException(status_code=403, detail="Not authorized")
