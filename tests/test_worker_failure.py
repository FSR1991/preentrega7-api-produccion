from app.worker import process_message


class FakeStore:
    def __init__(self):
        self.updates = []

    def get_task(self, task_id):
        return {
            "task_id": task_id,
            "prompt": "Prueba de error controlado",
            "status": "PENDING",
            "requires_approval": False,
        }

    def update_task(self, task_id, status, **kwargs):
        self.updates.append({
            "task_id": task_id,
            "status": status,
            **kwargs,
        })


class FailingGraph:
    def invoke(self, *args, **kwargs):
        raise RuntimeError("Fallo simulado para la prueba")


def test_worker_marks_task_failed_when_graph_raises():
    store = FakeStore()
    task_id = "test-worker-failure"

    process_message(
        {
            "action": "execute",
            "task_id": task_id,
        },
        store,
        FailingGraph(),
    )

    statuses = [update["status"] for update in store.updates]

    assert statuses == ["RUNNING", "FAILED"]
    assert "RuntimeError" in store.updates[-1]["error"]
    assert "Fallo simulado" in store.updates[-1]["error"]
    assert store.updates[-1]["finished_at"] is not None