from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError

from app.criticality import classify_criticality
from app.redis_store import create_redis_client
from app.task_store import TaskStore


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=10000)


class ApprovalRequest(BaseModel):
    approved: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = create_redis_client()

    try:
        await run_in_threadpool(client.ping)

        app.state.redis = client
        app.state.task_store = TaskStore(client)

        yield
    finally:
        await run_in_threadpool(client.close)


app = FastAPI(
    title="Pre-entrega 7 - API de producción",
    version="1.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health(request: Request):
    try:
        await run_in_threadpool(request.app.state.redis.ping)

        return {
            "status": "ok",
            "redis": "connected",
        }
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis no está disponible.",
        ) from exc


@app.post(
    "/tasks",
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_task(payload: TaskRequest, request: Request):
    task_id = str(uuid4())

    requires_approval, reason = classify_criticality(
        payload.prompt
    )

    task = {
        "task_id": task_id,
        "prompt": payload.prompt,
        "requires_approval": requires_approval,
        "criticality_reason": reason,
    }

    try:
        await run_in_threadpool(
            request.app.state.task_store.create_task,
            task,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo encolar la tarea.",
        ) from exc

    return {
        "job_id": task_id,
        "status": "PENDING",
        "requires_approval": requires_approval,
        "criticality_reason": reason,
    }


@app.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    try:
        task = await run_in_threadpool(
            request.app.state.task_store.get_task,
            task_id,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo consultar la tarea.",
        ) from exc

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        )

    return task


@app.post("/tasks/{task_id}/approve")
async def approve_task(
    task_id: str,
    payload: ApprovalRequest,
    request: Request,
):
    store = request.app.state.task_store

    try:
        await run_in_threadpool(
            store.enqueue_approval,
            task_id,
            payload.approved,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo registrar la decisión.",
        ) from exc

    return {
        "job_id": task_id,
        "status": "RESUME_QUEUED",
        "approved": payload.approved,
    }