"""Durable recorded-memory records and jobs; independent of model and queue SDKs."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict
import json
import os
from uuid import uuid4

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import label, timestamp, utc_now
from teach_and_find.storage import AssistantError, EvidenceStore


TERMINAL = {"succeeded", "inconclusive", "failed", "cancelled", "interrupted"}


def encode(value) -> str:
    try:
        return json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise AssistantError(
            "INVALID_MEMORY_RECORD", "Memory metadata must be finite JSON."
        ) from error


class MemoryService:
    def __init__(self, store: EvidenceStore, settings: Settings):
        self.store, self.settings, self.db = store, settings, store.db

    @staticmethod
    def mode(mode):
        if mode not in {"synthetic", "replay", "physical"}:
            raise AssistantError("INVALID_MODE", "Unsupported evidence mode.")

    def require_enabled(self):
        if not self.settings.memory.enabled:
            raise AssistantError(
                "MEMORY_DISABLED",
                "Research memory is disabled on this host; no fallback.",
            )

    def register_view(self, region_name: str, viewpoint_name: str) -> dict:
        self.require_enabled()
        region_name, viewpoint_name = label(region_name), label(viewpoint_name)
        with self.db:
            row = self.db.execute(
                "SELECT id FROM memory_regions WHERE name_key=?",
                (region_name.casefold(),),
            ).fetchone()
            region_id = row[0] if row else str(uuid4())
            if not row:
                self.db.execute(
                    "INSERT INTO memory_regions VALUES (?,?,?,?)",
                    (region_id, region_name, region_name.casefold(), utc_now()),
                )
            row = self.db.execute(
                "SELECT id FROM memory_views WHERE region_id=? AND name_key=?",
                (region_id, viewpoint_name.casefold()),
            ).fetchone()
            view_id = row[0] if row else str(uuid4())
            if not row:
                self.db.execute(
                    "INSERT INTO memory_views VALUES (?,?,?,?,?)",
                    (
                        view_id,
                        region_id,
                        viewpoint_name,
                        viewpoint_name.casefold(),
                        utc_now(),
                    ),
                )
        return {
            "id": view_id,
            "region_id": region_id,
            "name": viewpoint_name,
            "region_name": region_name,
            "source": "operator_registered",
            "pose": None,
        }

    def episode(self, name: str, mode: str) -> dict:
        self.require_enabled()
        self.mode(mode)
        record = {
            "id": str(uuid4()),
            "name": label(name),
            "mode": mode,
            "created_at": utc_now(),
        }
        with self.db:
            self.db.execute(
                "INSERT INTO memory_episodes VALUES (?,?,?,?)", tuple(record.values())
            )
        return record

    def existing(self, mode: str, key: str, kind: str, request: dict) -> dict | None:
        self.mode(mode)
        key = label(key)
        row = self.db.execute(
            "SELECT id,kind,payload_json FROM memory_jobs WHERE mode=? AND request_key=?",
            (mode, key),
        ).fetchone()
        if row:
            if (
                row["kind"] != kind
                or json.loads(row["payload_json"])["request"] != request
            ):
                raise AssistantError(
                    "IDEMPOTENCY_CONFLICT",
                    "This request key was used for different memory input.",
                )
            return self.job(row["id"], mode)
        return None

    def _insert_job(
        self, kind: str, mode: str, key: str, request: dict, **payload
    ) -> str:
        job_id = str(uuid4())
        payload.update(
            request=request,
            model=self.settings.memory.model,
            profile=asdict(self.settings.memory),
        )
        self.db.execute(
            """INSERT INTO memory_jobs
            (id,kind,mode,request_key,payload_json,created_at,status,stage)
            VALUES (?,?,?,?,?,?,'queued','queued')""",
            (job_id, kind, mode, label(key), encode(payload), utc_now()),
        )
        return job_id

    def capture(
        self, frame: CameraFrame, episode_id: str, view_id: str, key: str, mode: str
    ) -> dict:
        self.require_enabled()
        self.mode(mode)
        request = {
            "frame_id": frame.frame_id,
            "episode_id": episode_id,
            "view_id": view_id,
        }
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.existing(mode, key, "capture", request)
            if previous:
                self.db.rollback()
                return previous
            if not self.db.execute(
                "SELECT 1 FROM memory_episodes WHERE id=? AND mode=?",
                (episode_id, mode),
            ).fetchone():
                raise AssistantError(
                    "EPISODE_NOT_FOUND",
                    "Choose an episode in the current evidence mode.",
                )
            if not self.db.execute(
                "SELECT 1 FROM memory_views WHERE id=?", (view_id,)
            ).fetchone():
                raise AssistantError(
                    "VIEW_NOT_FOUND", "Register a viewpoint before capturing memory."
                )
            if self.db.execute(
                "SELECT 1 FROM memory_captures WHERE episode_id=? AND view_id=?",
                (episode_id, view_id),
            ).fetchone():
                raise AssistantError(
                    "CAPTURE_CONFLICT",
                    "This episode already has a capture at this viewpoint. Create a new episode.",
                )
            provenance = encode(
                {
                    **frame.provenance,
                    "region_source": "operator_registered",
                    "pose": frame.provenance.get("pose"),
                    "capture_clock_uncertainty_s": frame.provenance.get(
                        "capture_clock_uncertainty_s"
                    ),
                    "freshness_verified": frame.freshness_verified,
                    "age_at_receipt_s": frame.age_at_receipt_s,
                }
            )
            captured_at = timestamp(frame.captured_at)
            capture_id = str(uuid4())
            digest = self.store.save_image(frame.image)
            self.db.execute(
                "INSERT INTO memory_captures VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    capture_id,
                    episode_id,
                    view_id,
                    frame.frame_id,
                    mode,
                    captured_at,
                    utc_now(),
                    digest,
                    provenance,
                ),
            )
            job_id = self._insert_job(
                "capture", mode, key, request, capture_id=capture_id
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.job(job_id, mode)

    def captures(
        self,
        mode: str,
        episode_ids: list[str] | None = None,
        *,
        ready_only=False,
        limit=None,
        capture_id: str | None = None,
        newest=False,
    ) -> list[dict]:
        self.mode(mode)
        where, params = "c.mode=?", [mode]
        if capture_id is not None:
            where += " AND c.id=?"
            params.append(capture_id)
        if episode_ids is not None:
            if not episode_ids:
                return []
            where += " AND c.episode_id IN (" + ",".join("?" for _ in episode_ids) + ")"
            params.extend(episode_ids)
        if ready_only:
            where += " AND d.capture_id IS NOT NULL"
        params.append(limit or self.settings.memory.max_snapshot_captures + 1)
        order = "DESC" if newest else "ASC"
        rows = self.db.execute(
            f"""SELECT c.*, e.name AS episode_name, v.name AS view_name,
            r.id AS region_id,r.name AS region_name,d.description_json,d.model,
            d.provenance_json AS description_provenance_json
            FROM memory_captures c JOIN memory_episodes e ON e.id=c.episode_id
            JOIN memory_views v ON v.id=c.view_id JOIN memory_regions r ON r.id=v.region_id
            LEFT JOIN memory_descriptions d ON d.capture_id=c.id
            WHERE {where} ORDER BY c.captured_at {order},c.id {order} LIMIT ?""",
            params,
        )
        return [
            {
                **dict(row),
                "provenance": json.loads(row["provenance_json"]),
                "description_provenance": json.loads(row["description_provenance_json"])
                if row["description_provenance_json"]
                else None,
                "description": json.loads(row["description_json"])
                if row["description_json"]
                else None,
            }
            for row in rows
        ]

    def question(
        self, question: str, episode_ids: list[str], key: str, mode: str
    ) -> dict:
        self.require_enabled()
        question = question.strip()
        if (
            not question
            or len(question) > 2000
            or not 1 <= len(episode_ids) <= self.settings.memory.max_snapshot_captures
        ):
            raise AssistantError(
                "INVALID_MEMORY_QUESTION",
                "Enter a question and select a bounded set of episodes.",
            )
        request = {
            "question": question,
            "episode_ids": sorted(set(episode_ids)),
            "scope": "recorded_memory",
        }
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.existing(mode, key, "question", request)
            if previous:
                self.db.rollback()
                return previous
            for episode_id in request["episode_ids"]:
                if not self.db.execute(
                    "SELECT 1 FROM memory_episodes WHERE id=? AND mode=?",
                    (episode_id, mode),
                ).fetchone():
                    raise AssistantError(
                        "EPISODE_NOT_FOUND",
                        "One of the selected episodes is unavailable in this mode.",
                    )
            captures = self.captures(mode, request["episode_ids"])
            if not captures:
                raise AssistantError(
                    "MEMORY_EVIDENCE_REQUIRED",
                    "Complete a capture description before asking memory.",
                )
            if len(captures) > self.settings.memory.max_snapshot_captures:
                raise AssistantError(
                    "MEMORY_BUDGET_EXCEEDED",
                    "Select fewer captures; the snapshot will not be silently truncated.",
                )
            if {c["episode_id"] for c in captures} != set(request["episode_ids"]):
                raise AssistantError(
                    "MEMORY_EVIDENCE_REQUIRED",
                    "Every selected episode needs a completed capture.",
                )
            if any(c["description"] is None for c in captures):
                raise AssistantError(
                    "MEMORY_DESCRIPTION_REQUIRED",
                    "Every capture in the selected episodes needs a completed description; none will be silently omitted.",
                )
            job_id = self._insert_job("question", mode, key, request, snapshot=captures)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.job(job_id, mode)

    def job(self, job_id: str, mode: str, *, internal=False) -> dict:
        self.mode(mode)
        row = self.db.execute(
            "SELECT * FROM memory_jobs WHERE id=? AND mode=?", (job_id, mode)
        ).fetchone()
        if not row:
            raise AssistantError(
                "MEMORY_JOB_NOT_FOUND", "Memory job not found in this evidence mode."
            )
        record = dict(row)
        payload = json.loads(record.pop("payload_json"))
        record["model"] = payload["model"]
        record["request"] = payload["request"]
        raw_result = record.pop("result_json")
        record["result"] = json.loads(raw_result) if raw_result else None
        record["steps"] = [
            {
                "stage": s["stage"],
                "created_at": s["created_at"],
                **json.loads(s["record_json"]),
            }
            for s in self.db.execute(
                "SELECT * FROM memory_steps WHERE job_id=? ORDER BY ordinal", (job_id,)
            )
        ]
        if internal:
            record["payload"] = payload
        return record

    def cancel(self, job_id: str, mode: str) -> dict:
        self.job(job_id, mode)
        with self.db:
            self.db.execute(
                "UPDATE memory_jobs SET status='cancelled',stage='cancelled',finished_at=? WHERE id=? AND status IN ('queued','running')",
                (utc_now(), job_id),
            )
        return self.job(job_id, mode)

    def claim(self, job_id: str, worker_id: str) -> dict | None:
        with self.db:
            changed = self.db.execute(
                "UPDATE memory_jobs SET status='running',stage='starting',started_at=?,worker_id=? WHERE id=? AND status='queued'",
                (utc_now(), worker_id, job_id),
            ).rowcount
        if not changed:
            return None
        mode = self.db.execute(
            "SELECT mode FROM memory_jobs WHERE id=?", (job_id,)
        ).fetchone()[0]
        return self.job(job_id, mode, internal=True)

    def check_running(self, job_id: str) -> None:
        row = self.db.execute(
            "SELECT status FROM memory_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not row or row[0] != "running":
            raise AssistantError(
                "MEMORY_CANCELLED", "This memory job is no longer running."
            )

    def step(self, job_id: str, stage: str, record: dict) -> None:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.check_running(job_id)
            ordinal = self.db.execute(
                "SELECT COALESCE(MAX(ordinal),0)+1 FROM memory_steps WHERE job_id=?",
                (job_id,),
            ).fetchone()[0]
            self.db.execute(
                "INSERT INTO memory_steps VALUES (?,?,?,?,?)",
                (job_id, ordinal, utc_now(), stage, encode(record)),
            )
            self.db.execute(
                "UPDATE memory_jobs SET stage=? WHERE id=? AND status='running'",
                (stage, job_id),
            )

    def finish(
        self,
        job: dict,
        status: str,
        result: dict | None = None,
        error_code: str | None = None,
    ):
        if status not in TERMINAL:
            raise ValueError("Invalid terminal job state")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.check_running(job["id"])
            if status == "succeeded" and job["kind"] == "capture":
                capture_id = job["payload"]["capture_id"]
                self.db.execute(
                    "INSERT INTO memory_descriptions VALUES (?,?,?,?,?)",
                    (
                        capture_id,
                        utc_now(),
                        job["model"],
                        encode(result["description"]),
                        encode(result["provenance"]),
                    ),
                )
            self.db.execute(
                "UPDATE memory_jobs SET status=?,stage=?,finished_at=?,result_json=?,error_code=? WHERE id=? AND status='running'",
                (
                    status,
                    status,
                    utc_now(),
                    encode(result) if result is not None else None,
                    error_code,
                    job["id"],
                ),
            )

    def worker_seen(self, worker_id: str, status="ready", error_code=None):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO memory_worker VALUES (1,?,?,?,?,?)",
                (worker_id, os.getpid(), utc_now(), status, error_code),
            )

    def interrupt(self):
        with self.db:
            self.db.execute(
                "UPDATE memory_jobs SET status='interrupted',stage='interrupted',finished_at=?,error_code='WORKER_INTERRUPTED' WHERE status='running'",
                (utc_now(),),
            )

    def overview(self, mode: str) -> dict:
        self.mode(mode)
        worker = self.db.execute("SELECT * FROM memory_worker WHERE id=1").fetchone()
        worker = dict(worker) if worker else None
        if worker:
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(worker["seen_at"])
            ).total_seconds()
            worker["alive"] = (
                age <= self.settings.memory.worker_stale_s
                and worker["status"] == "ready"
            )
        views = [
            dict(row)
            for row in self.db.execute(
                "SELECT v.id,v.name,r.name AS region_name,r.id AS region_id FROM memory_views v JOIN memory_regions r ON r.id=v.region_id ORDER BY r.name,v.name"
            )
        ]
        episodes = [
            dict(row)
            for row in self.db.execute(
                "SELECT * FROM memory_episodes WHERE mode=? ORDER BY created_at DESC LIMIT ?",
                (mode, self.settings.memory.history_limit),
            )
        ]
        jobs = [
            self.job(row[0], mode)
            for row in self.db.execute(
                "SELECT id FROM memory_jobs WHERE mode=? ORDER BY created_at DESC,id LIMIT ?",
                (mode, self.settings.memory.history_limit),
            )
        ]
        return {
            "schema_version": 1,
            "enabled": self.settings.memory.enabled,
            "model": self.settings.memory.model,
            "mode": mode,
            "scope": "recorded_memory",
            "worker": worker,
            "views": views,
            "episodes": episodes,
            "captures": self.captures(
                mode, limit=self.settings.memory.history_limit, newest=True
            ),
            "jobs": jobs,
        }
