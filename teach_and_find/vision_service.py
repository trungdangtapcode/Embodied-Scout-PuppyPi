"""Immutable visual inference snapshots over the existing durable job/evidence store."""

from dataclasses import asdict
from datetime import datetime, timezone
import os

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import timestamp, utc_now
from teach_and_find.memory_service import MemoryService
from teach_and_find.storage import AssistantError, EvidenceStore


class VisionService:
    def __init__(self, store: EvidenceStore, settings: Settings):
        self.store, self.settings = store, settings
        self.jobs = MemoryService(store, settings)

    def enqueue(
        self, frames: list[CameraFrame], object_ids: list[str], key: str, mode: str
    ) -> dict:
        cfg = self.settings.vision
        if not cfg.enabled:
            raise AssistantError(
                "VISION_DISABLED", "Learned vision is disabled; no fallback."
            )
        self.jobs.mode(mode)
        if not frames or len(frames) > cfg.max_frames:
            raise AssistantError(
                "VISION_WINDOW_INVALID", "Choose a bounded, nonempty camera window."
            )
        if (
            not object_ids
            or len(set(object_ids)) != len(object_ids)
            or len(object_ids) > cfg.max_objects
        ):
            raise AssistantError(
                "VISION_REFERENCES_INVALID",
                "Select distinct enrolled objects within the model budget.",
            )
        request = {"frame_id": frames[-1].frame_id, "object_ids": object_ids}
        existing = self.jobs.existing(mode, key, "vision", request)
        if existing:
            return existing
        if len({f.frame_id for f in frames}) != len(frames):
            raise AssistantError("VISION_WINDOW_INVALID", "Frame IDs must be unique.")
        identity = None
        previous = None
        snapshots = []
        for f in frames:
            camera = (f.provenance.get("camera_id"), f.provenance.get("session_id"))
            if not all(camera) or (identity is not None and camera != identity):
                raise AssistantError(
                    "VISION_CAMERA_MISMATCH",
                    "One identified camera/session is required per window.",
                )
            identity = camera
            captured = timestamp(f.captured_at)
            dt = datetime.fromisoformat(captured)
            if (
                previous is not None
                and not 0 < (dt - previous).total_seconds() <= cfg.max_frame_gap_s
            ):
                raise AssistantError(
                    "VISION_TIME_INVALID",
                    "Frames must be ordered with bounded capture gaps.",
                )
            if captured > utc_now():
                raise AssistantError(
                    "VISION_TIME_INVALID", "Capture time is in the future."
                )
            previous = dt
            snapshots.append(
                {
                    "frame_id": f.frame_id,
                    "captured_at": captured,
                    "image_sha": self.store.save_image(f.image),
                    "provenance": f.provenance,
                }
            )
        references = []
        # Read image references only. Legacy CV2 embeddings are never consumed.
        for oid in object_ids:
            obj = self.store.db.execute(
                "SELECT name FROM objects WHERE id=? AND archived_at IS NULL", (oid,)
            ).fetchone()
            if not obj:
                raise AssistantError(
                    "OBJECT_NOT_FOUND", "A selected object is missing or archived."
                )
            refs = [
                r[0]
                for r in self.store.db.execute(
                    "SELECT image_sha FROM reference_views WHERE object_id=? ORDER BY ordinal",
                    (oid,),
                )
            ]
            if not 1 <= len(refs) <= cfg.max_references:
                raise AssistantError(
                    "VISION_REFERENCES_INVALID",
                    "Reference count exceeds the supported prompt budget.",
                )
            for sha in refs:
                self.store.image_bytes(sha)
            references.append(
                {
                    "object_id": oid,
                    "name": obj[0],
                    "image_shas": refs,
                    "label_source": "enrollment_input_not_inferred_identity",
                }
            )
        with self.store.db:
            # Serialize key checking with insertion; a racing retry cannot run twice.
            self.store.db.execute("BEGIN IMMEDIATE")
            existing = self.jobs.existing(mode, key, "vision", request)
            if existing:
                return existing
            job_id = self.jobs.insert_job(
                "vision",
                mode,
                key,
                request,
                model=cfg.model,
                profile=asdict(cfg),
                frames=snapshots,
                references=references,
            )
        return self.job(job_id, mode)

    def job(self, job_id: str, mode: str, *, internal=False) -> dict:
        job = self.jobs.job(job_id, mode, internal=internal)
        if job["kind"] != "vision":
            raise AssistantError(
                "VISION_JOB_NOT_FOUND", "Not a vision job in this evidence mode."
            )
        return job

    def cancel(self, job_id: str, mode: str) -> dict:
        self.job(job_id, mode)
        return self.jobs.cancel(job_id, mode)

    def interrupt(self):
        with self.store.db:
            self.store.db.execute(
                "UPDATE memory_jobs SET status='interrupted',stage='interrupted',finished_at=?,error_code='WORKER_INTERRUPTED' WHERE status='running' AND kind='vision'",
                (utc_now(),),
            )

    def worker_seen(self, worker_id: str, status="ready", error_code=None):
        with self.store.db:
            self.store.db.execute(
                "INSERT OR REPLACE INTO vision_worker VALUES (1,?,?,?,?,?)",
                (worker_id, os.getpid(), utc_now(), status, error_code),
            )

    def overview(self, mode: str) -> dict:
        self.jobs.mode(mode)
        row = self.store.db.execute("SELECT * FROM vision_worker WHERE id=1").fetchone()
        worker = dict(row) if row else None
        if worker:
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(worker["seen_at"])
            ).total_seconds()
            worker["alive"] = (
                age <= self.settings.vision.worker_stale_s
                and worker["status"] == "ready"
            )
        return {
            "schema_version": 1,
            "enabled": self.settings.vision.enabled,
            "mode": mode,
            "model": self.settings.vision.model,
            "method": "upstream_yoloe_savpe_segmentation_and_bytetrack",
            "worker": worker,
            "jobs": [
                self.job(r[0], mode)
                for r in self.store.db.execute(
                    "SELECT id FROM memory_jobs WHERE mode=? AND kind='vision' ORDER BY created_at DESC,id LIMIT ?",
                    (mode, self.settings.vision.history_limit),
                )
            ],
        }
