"""Optional real Huey transport; messages contain only a durable job ID."""

from pathlib import Path

from teach_and_find.config import Settings


def queue_for(settings: Settings):
    from huey import SqliteHuey

    root = Path(settings.assistant.data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return SqliteHuey(
        "puppypi_recorded_memory",
        filename=str(root / "memory-queue.sqlite3"),
        immediate=False,
        results=False,
    )


def tasks_for(settings: Settings):
    queue = queue_for(settings)

    @queue.task(name="puppypi.memory.execute", retries=0)
    def execute(job_id):
        from teach_and_find.memory_worker import execute_job

        execute_job(settings, job_id)

    return queue, execute


def dispatch(settings: Settings, job_id: str):
    from teach_and_find.storage import EvidenceStore
    from teach_and_find.library import utc_now

    with EvidenceStore(settings.assistant.data_dir) as store:
        row = store.db.execute(
            "SELECT status,dispatched_at FROM memory_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not row or row[0] != "queued" or row[1] is not None:
            return
        _, task = tasks_for(settings)
        task(job_id)
        # A crash here can duplicate a message, but the worker's atomic claim
        # prevents duplicate inference. Running jobs are never automatically retried.
        with store.db:
            store.db.execute(
                "UPDATE memory_jobs SET dispatched_at=? WHERE id=? AND status='queued'",
                (utc_now(), job_id),
            )
