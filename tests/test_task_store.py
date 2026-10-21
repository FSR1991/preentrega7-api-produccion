import json
from uuid import uuid4

import pytest
from redis import Redis

from app.config import get_redis_url
from app.task_store import TaskStore


@pytest.fixture
def redis_client():
    client = Redis.from_url(
        get_redis_url(),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=10,
    )
    client.ping()
    yield client
    client.close()


@pytest.fixture
def store(redis_client):
    return TaskStore(redis_client)


@pytest.fixture
def task_id():
    return str(uuid4())


def cleanup_task(store, redis_client, task_id):
    redis_client.delete(store.task_key(task_id))

    # Retira solamente mensajes de esta tarea de la cola de pruebas.
    messages = redis_client.lrange(store.QUEUE, 0, -1)
    for message in messages:
        try:
            if json.loads(message).get("task_id") == task_id:
                redis_client.lrem(store.QUEUE, 1, message)
        except (TypeError, json.JSONDecodeError):
            continue


def test_create_task_and_read_pending(store, redis_client, task_id):
    try:
        store.create_task({
            "task_id": task_id,
            "prompt": "Prueba automatizada",
            "requires_approval": False,
        })

        task = store.get_task(task_id)

        assert task is not None
        assert task["status"] == "PENDING"
        assert task["prompt"] == "Prueba automatizada"

        # Buscar el mensaje de esta tarea, aunque el worker
        # haya consumido ya el mensaje de la cola.
        raw = redis_client.hgetall(store.task_key(task_id))
        assert raw
        assert raw["status"] in {"PENDING", "RUNNING", "DONE"}

    finally:
        cleanup_task(store, redis_client, task_id)


def test_duplicate_task_is_rejected(store, redis_client, task_id):
    payload = {
        "task_id": task_id,
        "prompt": "Tarea duplicada",
        "requires_approval": False,
    }

    try:
        store.create_task(payload)

        with pytest.raises(ValueError):
            store.create_task(payload)
    finally:
        cleanup_task(store, redis_client, task_id)


def test_update_saves_metrics(store, redis_client, task_id):
    try:
        store.create_task({
            "task_id": task_id,
            "prompt": "Guardar métricas",
            "requires_approval": False,
        })

        store.update_task(
            task_id,
            "DONE",
            result="Correcto",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0000045,
            started_at=1000.0,
            finished_at=1001.5,
            duration_seconds=1.5,
        )

        task = store.get_task(task_id)
        assert task is not None
        assert task["status"] == "DONE"
        assert task["result"] == "Correcto"
        assert task["input_tokens"] == 10
        assert task["output_tokens"] == 5
        assert task["cost_usd"] == pytest.approx(0.0000045)
        assert task["duration_seconds"] == pytest.approx(1.5)
    finally:
        cleanup_task(store, redis_client, task_id)


def test_missing_task_returns_none(store):
    assert store.get_task(str(uuid4())) is None


def test_approval_requires_waiting_state(store, redis_client, task_id):
    try:
        store.create_task({
            "task_id": task_id,
            "prompt": "Prueba de aprobación",
            "requires_approval": True,
        })

        with pytest.raises(ValueError):
            store.enqueue_approval(task_id, approved=True)
    finally:
        cleanup_task(store, redis_client, task_id)