import json
import time
from typing import Any

from redis import Redis
from redis.exceptions import WatchError


class TaskStore:
    """Gestiona tareas, estados y cola Redis."""

    QUEUE = "preentrega7:queue"
    PREFIX = "preentrega7:task:"

    VALID_STATUSES = {
        "PENDING",
        "RUNNING",
        "WAITING_APPROVAL",
        "APPROVAL_QUEUED",
        "DONE",
        "REJECTED",
        "FAILED",
    }

    def __init__(self, client: Redis) -> None:
        self.client = client

    @classmethod
    def task_key(cls, task_id: str) -> str:
        return f"{cls.PREFIX}{task_id}"

    def create_task(self, task: dict[str, Any]) -> None:
        task_id = task["task_id"]
        key = self.task_key(task_id)

        payload = {
            **task,
            "status": "PENDING",
            "created_at": time.time(),
        }

        message = json.dumps({
            "action": "execute",
            "task_id": task_id,
        })

        script = """
        if redis.call('EXISTS', KEYS[1]) == 1 then
            return 0
        end

        redis.call(
            'HSET', KEYS[1],
            'data', ARGV[1],
            'status', 'PENDING'
        )

        redis.call('RPUSH', KEYS[2], ARGV[2])
        return 1
        """

        created = self.client.eval(
            script,
            2,
            key,
            self.QUEUE,
            json.dumps(payload, ensure_ascii=False),
            message,
        )

        if not created:
            raise ValueError(f"La tarea {task_id} ya existe.")

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        raw = self.client.hgetall(self.task_key(task_id))

        if not raw or "data" not in raw:
            return None

        task = json.loads(raw["data"])
        task["status"] = raw.get(
            "status",
            task.get("status", "PENDING"),
        )

        numeric_fields = {
            "input_tokens": int,
            "output_tokens": int,
            "cost_usd": float,
            "created_at": float,
            "started_at": float,
            "finished_at": float,
            "duration_seconds": float,
        }

        for field, converter in numeric_fields.items():
            value = raw.get(field)
            if value is not None:
                task[field] = converter(value)

        for field in ("result", "error", "approval"):
            value = raw.get(field)
            if value is not None:
                task[field] = value

        return task

    def update_task(
        self,
        task_id: str,
        status: str,
        *,
        result: str | None = None,
        error: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        approval: str | None = None,
        started_at: float | None = None,
        finished_at: float | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Estado no válido: {status}")

        key = self.task_key(task_id)

        optional = {
            "result": result,
            "error": error,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "approval": approval,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration_seconds,
        }

        updates: dict[str, str] = {"status": status}

        for field, value in optional.items():
            if value is not None:
                updates[field] = str(value)

        for attempt in range(3):
            try:
                with self.client.pipeline(transaction=True) as pipe:
                    pipe.watch(key)
                    raw = pipe.hget(key, "data")

                    if raw is None:
                        pipe.unwatch()
                        raise KeyError(
                            f"No existe la tarea {task_id}."
                        )

                    data = json.loads(raw)
                    data["status"] = status

                    for field, value in optional.items():
                        if value is not None:
                            data[field] = value

                    pipe.multi()
                    pipe.hset(key, mapping=updates)
                    pipe.hset(
                        key,
                        "data",
                        json.dumps(data, ensure_ascii=False),
                    )
                    pipe.execute()

                return

            except WatchError:
                if attempt == 2:
                    raise

    def enqueue_approval(
        self,
        task_id: str,
        approved: bool,
    ) -> None:
        key = self.task_key(task_id)

        message = json.dumps({
            "action": "resume",
            "task_id": task_id,
            "approved": approved,
        })

        decision = "approved" if approved else "rejected"

        script = """
        local state = redis.call('HGET', KEYS[1], 'status')

        if not state then
            return -1
        end

        if state ~= 'WAITING_APPROVAL' then
            return 0
        end

        local raw = redis.call('HGET', KEYS[1], 'data')

        if not raw then
            return -2
        end

        local ok, data = pcall(cjson.decode, raw)

        if not ok or type(data) ~= 'table' then
            return -2
        end

        data['status'] = 'APPROVAL_QUEUED'
        data['approval'] = ARGV[2]

        redis.call(
            'HSET', KEYS[1],
            'data', cjson.encode(data),
            'status', 'APPROVAL_QUEUED',
            'approval', ARGV[2]
        )

        redis.call('RPUSH', KEYS[2], ARGV[1])

        return 1
        """

        result = self.client.eval(
            script,
            2,
            key,
            self.QUEUE,
            message,
            decision,
        )

        if result == -1:
            raise KeyError(f"No existe la tarea {task_id}.")

        if result == -2:
            raise ValueError(
                "La tarea tiene datos ausentes o inválidos en Redis."
            )

        if result == 0:
            raise ValueError(
                "La tarea no está esperando aprobación "
                "o ya recibió una decisión."
            )

    def dequeue(self, timeout: int = 5) -> dict[str, Any] | None:
        item = self.client.blpop(self.QUEUE, timeout=timeout)
        return json.loads(item[1]) if item else None