"""Versioned SQLite metadata and content-addressed image evidence."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile

import cv2
import numpy as np


class AssistantError(ValueError):
    """Stable error code for operator-facing adapters."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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
