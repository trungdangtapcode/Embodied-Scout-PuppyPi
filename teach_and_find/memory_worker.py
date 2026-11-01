"""Independent recorded-memory worker. Never imports or sends robot commands."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
import threading
from uuid import uuid4

from teach_and_find.config import MemorySettings, Settings
from teach_and_find.memory_service import MemoryService
from teach_and_find.storage import AssistantError, EvidenceStore


WORKER_ID = str(uuid4())


def execute_job(settings: Settings, job_id: str, *, adapter_factory=None):
    from dataclasses import replace
    from teach_and_find.mind_palace_adapter import MindPalaceAdapter

    with EvidenceStore(settings.assistant.data_dir) as store:
        service = MemoryService(store, settings)
        service.require_enabled()
        kind = store.db.execute("SELECT kind FROM memory_jobs WHERE id=?", (job_id,)).fetchone()
        if kind and kind[0] not in {"capture", "question"}:
            raise AssistantError("WRONG_WORKER", "This job requires another worker.")
        job = service.claim(job_id, WORKER_ID)
        if job is None:
            return
        try:
            cfg = replace(settings, memory=MemorySettings(**job["payload"]["profile"]))
            adapter = (adapter_factory or MindPalaceAdapter)(
                cfg,
                lambda stage, record: service.step(job_id, stage, record),
                lambda: service.check_running(job_id),
            )
            if job["kind"] == "capture":
                captures = service.captures(
                    job["mode"], capture_id=job["payload"]["capture_id"]
                )
                if len(captures) != 1:
                    raise AssistantError(
                        "MEMORY_CAPTURE_NOT_FOUND",
                        "The job's exact source capture is unavailable.",
                    )
                capture = captures[0]
                result = adapter.describe(
                    capture, store.images / (capture["image_sha"] + ".png")
                )
            else:
                snapshot = job["payload"]["snapshot"]
                result = adapter.question(
                    job["payload"]["request"]["question"],
                    snapshot,
                    {
                        c["id"]: str(store.images / (c["image_sha"] + ".png"))
                        for c in snapshot
                    },
                )
            state = (
                "inconclusive"
                if result.get("outcome") == "inconclusive"
                else "succeeded"
            )
            service.finish(job, state, result)
        except Exception as error:
            code = (
                error.code
                if isinstance(error, AssistantError)
                else "MEMORY_EXECUTION_FAILED"
            )
            if code != "MEMORY_CANCELLED":
                try:
                    service.finish(job, "failed", error_code=code)
                except AssistantError:
                    # Cancellation won the transaction; never overwrite it.
                    pass


def main():
    from teach_and_find.memory_queue import dispatch, tasks_for
    from teach_and_find.mind_palace_adapter import load_upstream

    settings = Settings()
    root = Path(settings.assistant.data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    with (root / "memory-worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A memory worker already owns this evidence store.")
        with EvidenceStore(root) as store:
            service = MemoryService(store, settings)
            service.require_enabled()
            service.interrupt()
            try:
                load_upstream(settings)
                if not os.environ.get("OPENAI_API_KEY"):
                    raise AssistantError(
                        "MODEL_KEY_REQUIRED",
                        "Export OPENAI_API_KEY in the worker environment.",
                    )
            except AssistantError as error:
                service.worker_seen(WORKER_ID, "failed", error.code)
                raise SystemExit(error.code)

        def heartbeat():
            while not stop.is_set():
                try:
                    with EvidenceStore(root) as store:
                        MemoryService(store, settings).worker_seen(WORKER_ID)
                        pending = [
                            row[0]
                            for row in store.db.execute(
                                "SELECT id FROM memory_jobs WHERE status='queued' AND dispatched_at IS NULL AND kind IN ('capture','question')"
                            )
                        ]
                    for job_id in pending:
                        dispatch(settings, job_id)
                except Exception:
                    # A failed heartbeat becomes visibly stale; no fake health.
                    pass
                stop.wait(settings.memory.heartbeat_s)

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        queue, _ = tasks_for(settings)
        consumer = queue.create_consumer(
            workers=1,
            worker_type="thread",
            periodic=False,
            initial_delay=settings.memory.polling_s,
            max_delay=settings.memory.polling_s,
        )
        try:
            consumer.run()
        finally:
            stop.set()
            thread.join(timeout=settings.memory.heartbeat_s + 2)
            with EvidenceStore(root) as store:
                service = MemoryService(store, settings)
                service.interrupt()
                service.worker_seen(WORKER_ID, "stopped")


if __name__ == "__main__":
    main()
