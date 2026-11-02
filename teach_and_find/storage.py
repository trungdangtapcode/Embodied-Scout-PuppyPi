"""Versioned SQLite metadata and content-addressed image evidence."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile

import cv2
import numpy as np


# Re-export preserves existing imports; domain rules use errors directly.
from teach_and_find.errors import AssistantError


# Each tuple is one migration from user_version N to N+1. Never edit a shipped
# migration; append a migration for subsequent schema changes.
MIGRATIONS = (
    (
        """CREATE TABLE objects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL,
            encoder_signature TEXT NOT NULL, embedding_dim INTEGER NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT)""",
        "CREATE UNIQUE INDEX active_object_names ON objects(name_key) WHERE archived_at IS NULL",
        """CREATE TABLE reference_views (
            object_id TEXT NOT NULL REFERENCES objects(id), ordinal INTEGER NOT NULL,
            image_sha TEXT NOT NULL, embedding BLOB NOT NULL, angle_deg REAL,
            PRIMARY KEY(object_id, ordinal))""",
        """CREATE TABLE observations (
            id TEXT PRIMARY KEY, object_id TEXT NOT NULL REFERENCES objects(id),
            station TEXT NOT NULL, assertion TEXT NOT NULL CHECK(assertion IN ('present','absent','unknown')),
            captured_at TEXT NOT NULL, recorded_at TEXT NOT NULL, image_sha TEXT NOT NULL,
            quality REAL NOT NULL, visibility REAL NOT NULL, source TEXT NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('synthetic','replay','physical')))""",
        "CREATE INDEX observation_history ON observations(object_id, captured_at, recorded_at)",
    ),
    (
        """CREATE TABLE checklists (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
            rules_json TEXT NOT NULL)""",
        """CREATE TABLE inspection_reports (
            id TEXT PRIMARY KEY, checklist_id TEXT NOT NULL REFERENCES checklists(id),
            created_at TEXT NOT NULL, report_json TEXT NOT NULL)""",
    ),
    ("ALTER TABLE observations ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'",),
    (
        """CREATE TABLE room_queries (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, mode TEXT NOT NULL,
            result_json TEXT NOT NULL)""",
        "CREATE INDEX room_query_history ON room_queries(mode, created_at DESC)",
        "CREATE INDEX room_timeline ON observations(mode, captured_at DESC, recorded_at DESC)",
        """CREATE TABLE scene_analyses (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, mode TEXT NOT NULL,
            result_json TEXT NOT NULL)""",
        """CREATE TABLE scene_confirmations (
            analysis_id TEXT NOT NULL REFERENCES scene_analyses(id),
            proposal_index INTEGER NOT NULL,
            observation_id TEXT NOT NULL REFERENCES observations(id),
            PRIMARY KEY(analysis_id, proposal_index))""",
    ),
    (
        """CREATE TABLE memory_regions (id TEXT PRIMARY KEY, name TEXT NOT NULL,
            name_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)""",
        """CREATE TABLE memory_views (id TEXT PRIMARY KEY, region_id TEXT NOT NULL
            REFERENCES memory_regions(id), name TEXT NOT NULL, name_key TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(region_id, name_key))""",
        """CREATE TABLE memory_episodes (id TEXT PRIMARY KEY, name TEXT NOT NULL,
            mode TEXT NOT NULL, created_at TEXT NOT NULL)""",
        """CREATE TABLE memory_captures (id TEXT PRIMARY KEY, episode_id TEXT NOT NULL
            REFERENCES memory_episodes(id), view_id TEXT NOT NULL REFERENCES memory_views(id),
            frame_id TEXT NOT NULL, mode TEXT NOT NULL, captured_at TEXT NOT NULL,
            received_at TEXT NOT NULL, image_sha TEXT NOT NULL, provenance_json TEXT NOT NULL,
            UNIQUE(episode_id, view_id))""",
        """CREATE TABLE memory_descriptions (capture_id TEXT PRIMARY KEY REFERENCES
            memory_captures(id), created_at TEXT NOT NULL, model TEXT NOT NULL,
            description_json TEXT NOT NULL, provenance_json TEXT NOT NULL)""",
        """CREATE TABLE memory_jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL,
            mode TEXT NOT NULL, request_key TEXT NOT NULL, payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
            started_at TEXT, finished_at TEXT, worker_id TEXT, dispatched_at TEXT,
            result_json TEXT, error_code TEXT, UNIQUE(mode, request_key))""",
        """CREATE TABLE memory_steps (job_id TEXT NOT NULL REFERENCES memory_jobs(id),
            ordinal INTEGER NOT NULL, created_at TEXT NOT NULL, stage TEXT NOT NULL,
            record_json TEXT NOT NULL, PRIMARY KEY(job_id, ordinal))""",
        "CREATE INDEX memory_job_history ON memory_jobs(mode, created_at DESC)",
        """CREATE TABLE memory_worker (id INTEGER PRIMARY KEY CHECK(id=1),
            worker_id TEXT NOT NULL, pid INTEGER NOT NULL, seen_at TEXT NOT NULL,
            status TEXT NOT NULL, error_code TEXT)""",
    ),
    (
        """CREATE TABLE vision_worker (id INTEGER PRIMARY KEY CHECK(id=1),
            worker_id TEXT NOT NULL, pid INTEGER NOT NULL, seen_at TEXT NOT NULL,
            status TEXT NOT NULL, error_code TEXT)""",
    ),
    (
        """CREATE TABLE tracking_sessions (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, mode TEXT NOT NULL, request_key TEXT NOT NULL,
            generation INTEGER NOT NULL, revision INTEGER NOT NULL,
            status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
            lease_until REAL NOT NULL, started_at REAL, anchor_json TEXT NOT NULL,
            prompt_json TEXT, preview_json TEXT, profile_json TEXT NOT NULL,
            error_code TEXT, error_json TEXT, dropped_frames INTEGER NOT NULL DEFAULT 0,
            evidence_bytes INTEGER NOT NULL DEFAULT 0)""",
        """CREATE UNIQUE INDEX tracking_request_key ON tracking_sessions(owner,mode,request_key)""",
        """CREATE TABLE tracking_frames (
            session_id TEXT NOT NULL REFERENCES tracking_sessions(id),
            sequence INTEGER NOT NULL, frame_id TEXT NOT NULL, record_json TEXT NOT NULL,
            PRIMARY KEY(session_id,sequence), UNIQUE(session_id,frame_id))""",
        """CREATE TABLE tracking_observations (
            session_id TEXT NOT NULL REFERENCES tracking_sessions(id), generation INTEGER NOT NULL,
            sequence INTEGER NOT NULL, record_json TEXT NOT NULL,
            PRIMARY KEY(session_id,generation,sequence))""",
        """CREATE TABLE tracking_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES tracking_sessions(id),
            generation INTEGER NOT NULL, at REAL NOT NULL, kind TEXT NOT NULL, record_json TEXT NOT NULL)""",
        """CREATE TABLE tracking_worker (id INTEGER PRIMARY KEY CHECK(id=1),
            pid INTEGER NOT NULL, seen_at REAL NOT NULL, status TEXT NOT NULL,
            error_json TEXT)""",
    ),
    (
        """CREATE TABLE tracking_streams (
            session_id TEXT PRIMARY KEY REFERENCES tracking_sessions(id),
            phase TEXT NOT NULL DEFAULT 'bootstrap', next_sequence INTEGER NOT NULL DEFAULT 1,
            claimed_sequence INTEGER NOT NULL DEFAULT 0, in_flight_sequence INTEGER,
            offered_frames INTEGER NOT NULL DEFAULT 0, processed_frames INTEGER NOT NULL DEFAULT 0,
            producer_replacements INTEGER NOT NULL DEFAULT 0, pending_replacements INTEGER NOT NULL DEFAULT 0,
            skipped_frames INTEGER NOT NULL DEFAULT 0, peak_live_pending INTEGER NOT NULL DEFAULT 0)""",
    ),
    (
        """CREATE TABLE searches (id TEXT PRIMARY KEY, object_id TEXT NOT NULL REFERENCES objects(id),
            owner TEXT NOT NULL, request_key TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
            result_json TEXT, error_json TEXT, mode TEXT NOT NULL, UNIQUE(owner,request_key))""",
        "CREATE UNIQUE INDEX one_active_search ON searches((1)) WHERE status IN ('queued','running')",
        """CREATE TABLE search_views (search_id TEXT NOT NULL REFERENCES searches(id), ordinal INTEGER NOT NULL,
            record_json TEXT NOT NULL, PRIMARY KEY(search_id,ordinal))""",
        """CREATE TABLE search_events (id INTEGER PRIMARY KEY AUTOINCREMENT, search_id TEXT NOT NULL REFERENCES searches(id),
            at TEXT NOT NULL, kind TEXT NOT NULL, record_json TEXT NOT NULL)""",
        "CREATE INDEX search_event_history ON search_events(search_id,id)",
        """CREATE TABLE model_sightings (id TEXT PRIMARY KEY, search_id TEXT NOT NULL REFERENCES searches(id),
            object_id TEXT NOT NULL REFERENCES objects(id), station TEXT NOT NULL,
            captured_at TEXT NOT NULL, record_json TEXT NOT NULL)""",
        "CREATE INDEX model_sighting_history ON model_sightings(object_id,captured_at DESC)",
        "CREATE TABLE search_worker (id INTEGER PRIMARY KEY CHECK(id=1), seen_at REAL NOT NULL, status TEXT NOT NULL)",
    ),
)


class EvidenceStore:
    def __init__(self, directory: str | Path) -> None:
        self.root = Path(directory).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.images = self.root / "images"
        self.images.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "assistant.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise AssistantError(
                    "SCHEMA_TOO_NEW", "Database needs a newer application version."
                )
            for index in range(version, len(MIGRATIONS)):
                for statement in MIGRATIONS[index]:
                    self.db.execute(statement)
                self.db.execute(f"PRAGMA user_version = {index + 1}")
            self.db.commit()
        except Exception:
            self.db.rollback()
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> EvidenceStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def save_image(self, image: np.ndarray) -> str:
        if (
            not isinstance(image, np.ndarray)
            or image.dtype != np.uint8
            or image.ndim != 3
            or image.shape[2] != 3
            or image.size == 0
        ):
            raise AssistantError(
                "INVALID_IMAGE", "Expected a nonempty uint8 BGR image."
            )
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise AssistantError("INVALID_IMAGE", "Unable to encode evidence image.")
        payload = encoded.tobytes()
        digest = hashlib.sha256(payload).hexdigest()
        destination = self.images / f"{digest}.png"
        if destination.exists():
            self.image_bytes(digest)
            return digest
        with tempfile.NamedTemporaryFile(dir=self.images, delete=False) as temporary:
            name = temporary.name
            try:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            except Exception:
                Path(name).unlink(missing_ok=True)
                raise
        try:
            os.replace(name, destination)
        finally:
            Path(name).unlink(missing_ok=True)
        return digest

    def image_bytes(self, digest: str) -> bytes:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise AssistantError("INVALID_EVIDENCE_ID", "Invalid evidence identifier.")
        try:
            payload = (self.images / f"{digest}.png").read_bytes()
        except FileNotFoundError as error:
            raise AssistantError(
                "EVIDENCE_MISSING", "A stored evidence image is missing."
            ) from error
        if hashlib.sha256(payload).hexdigest() != digest:
            raise AssistantError(
                "EVIDENCE_CORRUPT", "Evidence image failed its integrity check."
            )
        return payload

    def load_image(self, digest: str) -> np.ndarray:
        image = cv2.imdecode(
            np.frombuffer(self.image_bytes(digest), dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise AssistantError(
                "EVIDENCE_CORRUPT", "Evidence image cannot be decoded."
            )
        return image
