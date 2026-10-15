# app/routers/tasks.py

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app import models, schemas
from app.database import get_db
from app.routers.auth import get_current_active_user
from app.utils.helpers import calculate_priority_score, parse_tags
from app.utils.permissions import require_owner_or_admin

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/", response_model=List[schemas.TaskOut])
def list_tasks(
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Return all tasks. Optionally filter by status or owner."""
    # Issue: No pagination — returns ALL rows; will break under load
    tasks = db.query(models.Task).all()

    # Issue: filtering done in Python instead of the database
    if status:
        tasks = [t for t in tasks if t.status == status]
    if owner_id:
        tasks = [t for t in tasks if t.owner_id == owner_id]

    return tasks


@router.get("/search")
def search_tasks(
    q: str = Query(..., description="Search term"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Search tasks by title."""
    # Issue: raw SQL built with string formatting — SQL injection vulnerability
    raw = f"SELECT * FROM tasks WHERE title LIKE '%{q}%'"
    result = db.execute(text(raw)).fetchall()
    return [dict(row._mapping) for row in result]


@router.get("/{task_id}", response_model=schemas.TaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Issue: no authorization check — any authenticated user can read any task
    return task


@router.post("/", response_model=schemas.TaskOut, status_code=200)
# Issue: should return 201 Created
def create_task(
    task_data: schemas.TaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    task = models.Task(**task_data.model_dump(), owner_id=current_user.id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}", response_model=schemas.TaskOut)
def update_task(
    task_id: int,
    task_data: schemas.TaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    require_owner_or_admin(current_user, task.owner_id)
    update_data = task_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    require_owner_or_admin(current_user, task.owner_id)
    db.delete(task)
    db.commit()
    # Issue: should return 204 No Content; returning a body with 200 is inconsistent
    return {"message": "Task deleted"}


@router.get("/summary/by-user", response_model=List[dict])
def task_summary_by_user(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Return each user's task count and average priority score."""
    users = db.query(models.User).all()
    result = []

    for user in users:
        # Issue: N+1 query — one extra SELECT per user instead of a single JOIN/aggregation
        tasks = db.query(models.Task).filter(models.Task.owner_id == user.id).all()
        scores = [calculate_priority_score(t.priority, t.status) for t in tasks]
        avg_score = sum(scores) / len(scores) if scores else 0   # Issue: ZeroDivisionError if len == 0 (handled here, but pattern is fragile)

        result.append({
            "user_id": user.id,
            "username": user.username,
            "task_count": len(tasks),
            "avg_priority_score": round(avg_score, 2),
        })

    return result


@router.post("/{task_id}/comments", response_model=schemas.CommentOut)
def add_comment(
    task_id: int,
    comment_data: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    comment = models.Comment(
        content=comment_data.content,
        task_id=task_id,
        author_id=current_user.id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.get("/{task_id}/tags")
def get_task_tags(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"tags": parse_tags(task.tags)}
