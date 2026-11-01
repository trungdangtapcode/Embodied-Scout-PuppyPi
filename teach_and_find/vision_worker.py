"""Independent CPU vision consumer using the shared durable job protocol."""

from dataclasses import replace
import fcntl
from pathlib import Path
import threading
import time
from uuid import uuid4

from teach_and_find.config import Settings, VisionSettings
from teach_and_find.memory_queue import dispatch, tasks_for
from teach_and_find.storage import AssistantError, EvidenceStore
from teach_and_find.vision_service import VisionService


WORKER_ID = str(uuid4())


def execute_job(settings: Settings, job_id: str, *, adapter_factory=None):
    from teach_and_find.yoloe_adapter import YoloeAdapter

    with EvidenceStore(settings.assistant.data_dir) as store:
        service = VisionService(store, settings)
        row = store.db.execute(
            "SELECT kind FROM memory_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not row or row[0] != "vision":
            raise AssistantError(
                "WRONG_WORKER", "This worker accepts only visual inference jobs."
            )
        job = service.jobs.claim(job_id, WORKER_ID)
        if job is None:
            return
        try:
            profile = VisionSettings(**job["payload"]["profile"])
            if not settings.vision.enabled or not profile.enabled:
                raise AssistantError(
                    "VISION_DISABLED", "Vision is disabled; no substitute is selected."
                )
            deadline = time.monotonic() + profile.job_timeout_s

            def check():
                service.jobs.check_running(job_id)
                if time.monotonic() > deadline:
                    raise AssistantError(
                        "VISION_TIMEOUT", "CPU inference exceeded its job budget."
                    )

            adapter = (adapter_factory or YoloeAdapter)(
                profile,
                lambda stage, record: service.jobs.step(job_id, stage, record),
                check,
            )
            result = adapter.run(store, job["payload"])
            check()
            service.jobs.finish(job, "succeeded", result)
        except Exception as error:
            code = (
                error.code
                if isinstance(error, AssistantError)
                else "VISION_EXECUTION_FAILED"
            )
            if code != "MEMORY_CANCELLED":
                try:
                    service.jobs.step(
                        job_id,
                        "execution_error",
                        {
                            "code": code,
                            "exception_type": type(error).__name__,
                            "message": str(error)[:1000],
                            "required_profile": job["payload"]["profile"],
                        },
                    )
                    service.jobs.finish(job, "failed", error_code=code)
                except AssistantError:
                    pass  # Cancellation wins; no late result publication.


def main():
    settings = Settings()
    if not settings.vision.enabled:
        raise SystemExit("VISION_DISABLED")
    root = Path(settings.assistant.data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    with (root / "vision-worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A vision worker already owns this evidence store.")
        with EvidenceStore(root) as store:
            VisionService(store, settings).interrupt()

        def heartbeat():
            while not stop.is_set():
                try:
                    with EvidenceStore(root) as store:
                        VisionService(store, settings).worker_seen(WORKER_ID)
                        pending = [
                            r[0]
                            for r in store.db.execute(
                                "SELECT id FROM memory_jobs WHERE kind='vision' AND status='queued' AND dispatched_at IS NULL"
                            )
                        ]
                    for jid in pending:
                        dispatch(settings, jid, "vision")
                except Exception:
                    pass  # A missing heartbeat becomes visibly stale.
                stop.wait(settings.vision.heartbeat_s)

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        queue, _ = tasks_for(settings, "vision")
        consumer = queue.create_consumer(
            workers=1,
            worker_type="thread",
            periodic=False,
            initial_delay=settings.vision.polling_s,
            max_delay=settings.vision.polling_s,
        )
        try:
            consumer.run()
        finally:
            stop.set()
            thread.join(timeout=settings.vision.heartbeat_s + 2)
            with EvidenceStore(root) as store:
                service = VisionService(store, settings)
                service.interrupt()
                service.worker_seen(WORKER_ID, "stopped")


if __name__ == "__main__":
    main()
