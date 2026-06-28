from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.db.client import get_async_session
from src.db.models import Task, TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    obra_id: str | None = Field(default=None, max_length=32)
    author: str | None = Field(default=None, max_length=128)
    channel: str = Field(default="api", max_length=32)


class CreateTaskRequest(BaseModel):
    input: TaskInput


class TaskResponse(BaseModel):
    taskId: str
    status: str


class TaskDetailResponse(BaseModel):
    id: str
    status: str
    input: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def _enqueue_task(task_id: str) -> None:
    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue("obrabot", connection=redis_conn)
    queue.enqueue("src.worker.jobs.process_task", task_id, job_timeout=600)


@router.post("", response_model=TaskResponse, status_code=202)
async def create_task(
    body: CreateTaskRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    task = Task(status=TaskStatus.QUEUED, input=body.input.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)

    await asyncio.to_thread(_enqueue_task, str(task.id))

    return TaskResponse(taskId=str(task.id), status=task.status.value)


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> TaskDetailResponse:
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    return TaskDetailResponse(
        id=str(task.id),
        status=task.status.value,
        input=task.input,
        result=task.result,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )
