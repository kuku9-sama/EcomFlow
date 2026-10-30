import pytest
from ecomflow.database.store import Store
from ecomflow.jobs.tasks import TaskRunner, TaskFailed, configure_logging


def test_task_failure_and_retry(tmp_path):
    store = Store(str(tmp_path / "db"))
    runner = TaskRunner(store)
    configure_logging(str(tmp_path / "logs"))
    with pytest.raises(RuntimeError):
        runner.run(
            "sync", lambda: (_ for _ in ()).throw(RuntimeError("network failure"))
        )
    task = store.rows("SELECT * FROM tasks")[0]
    assert task["status"] == "FAILED" and task["error"] == "network failure"
    assert task["failed"] == 1 and task["ended_at"]
    assert len(store.rows("SELECT * FROM task_logs")) == 2
    assert "network failure" in (tmp_path / "logs/ecomflow.log").read_text()
    runner.run("sync", lambda: dict(total=2, success=2, failed=0), retry_of=task["id"])
    assert store.rows("SELECT * FROM tasks WHERE status='SUCCESS'")[0]["retries"] == 1


def test_partial_failure(tmp_path):
    store = Store(str(tmp_path / "db"))
    with pytest.raises(TaskFailed):
        TaskRunner(store).run("publish", lambda: dict(total=2, success=1, failed=1))
    task = store.rows("SELECT * FROM tasks")[0]
    assert (task["total"], task["success"], task["failed"]) == (2, 1, 1)
