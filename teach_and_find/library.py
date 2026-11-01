"""Durable object enrollment, appearance matching, and observation history."""

from __future__ import annotations

from collections import Counter
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
import io
import json
import math
import sqlite3
from uuid import uuid4

import numpy as np

from teach_and_find.config import Settings
from teach_and_find.perception.encoder import VisualEncoder, build_encoder
from teach_and_find.perception.memory import ObjectMemoryBank, ObjectRecord
from teach_and_find.storage import AssistantError, EvidenceStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as error:
        raise AssistantError(
            "INVALID_TIME", "Use an ISO 8601 timestamp with a timezone."
        ) from error
    if parsed.tzinfo is None:
        raise AssistantError("INVALID_TIME", "The timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def label(value: str) -> str:
    value = " ".join(value.split())
    if not value or len(value) > 120:
        raise AssistantError(
            "INVALID_LABEL", "Names and stations must contain 1 to 120 characters."
        )
    return value


def unit_score(value: float) -> float:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise AssistantError(
            "INVALID_SCORE", "Quality and visibility must be between zero and one."
        )
    return float(value)


def build_library(store: EvidenceStore, settings: Settings) -> ObjectLibrary:
    cfg = settings.perception
    if cfg.encoder_backend == "spatial_appearance":
        signature = f"spatial-appearance:v1:crop={cfg.crop_size}"
    elif cfg.encoder_backend == "torch_hub":
        revision = settings.assistant.encoder_revision
        if not revision:
            raise AssistantError(
                "ENCODER_REVISION_REQUIRED",
                "Set an explicit encoder/checkpoint revision before persistent enrollment; this generic adapter does not verify a weights digest.",
            )
        signature = (
            f"torch-hub:{cfg.torch_hub_repo}:{cfg.torch_hub_model}:{revision}:rgb224-v1"
        )
    else:
        raise AssistantError("UNKNOWN_ENCODER", "Unsupported encoder backend.")
    return ObjectLibrary(store, build_encoder(cfg), signature, settings)


class ObjectLibrary:
    def __init__(
        self,
        store: EvidenceStore,
        encoder: VisualEncoder,
        encoder_signature: str,
        settings: Settings | None = None,
    ) -> None:
        if not encoder_signature.strip():
            raise AssistantError(
                "ENCODER_REVISION_REQUIRED", "An encoder signature is required."
            )
        self.store = store
        self.encoder = encoder
        self.signature = encoder_signature
        self.settings = settings or Settings()

    def get(self, object_id: str, *, include_archived: bool = False) -> dict:
        row = self.store.db.execute(
            "SELECT * FROM objects WHERE id = ?", (object_id,)
        ).fetchone()
        if row is None or (row["archived_at"] and not include_archived):
            raise AssistantError("OBJECT_NOT_FOUND", "Object is missing or archived.")
        result = dict(row)
        result["references"] = [
            dict(item)
            for item in self.store.db.execute(
                "SELECT ordinal, image_sha, angle_deg FROM reference_views WHERE object_id = ? ORDER BY ordinal",
                (object_id,),
            )
        ]
        return result

    def list(self, *, include_archived: bool = False) -> list[dict]:
        clause = "" if include_archived else "WHERE archived_at IS NULL"
        return [
            self.get(row[0], include_archived=True)
            for row in self.store.db.execute(
                f"SELECT id FROM objects {clause} ORDER BY name_key, id"
            ).fetchall()
        ]

    def _compatible(self, record: dict) -> None:
        if (
            record["encoder_signature"] != self.signature
            or record["embedding_dim"] != self.encoder.embedding_dim
        ):
            raise AssistantError(
                "ENCODER_MISMATCH",
                "Stored prototypes use a different encoder or preprocessing revision.",
            )

    def teach(
        self,
        name: str,
        images: list[np.ndarray],
        angles: list[float] | None = None,
        *,
        object_id: str | None = None,
    ) -> dict:
        name = label(name)
        if not images:
            raise AssistantError(
                "REFERENCES_REQUIRED", "At least one reference image is required."
            )
        if angles is not None and (
            len(angles) != len(images) or not all(math.isfinite(a) for a in angles)
        ):
            raise AssistantError(
                "INVALID_ANGLES", "Provide one finite angle per reference image."
            )
        if object_id:
            self._compatible(self.get(object_id))
        prepared = []
        for index, image in enumerate(images):
            digest = self.store.save_image(image)
            embedding = np.asarray(self.encoder.embed(image), dtype=np.float32)
            if (
                embedding.shape != (self.encoder.embedding_dim,)
                or not np.isfinite(embedding).all()
                or np.linalg.norm(embedding) < 1e-8
            ):
                raise AssistantError(
                    "INVALID_EMBEDDING", "The encoder returned an unusable descriptor."
                )
            buffer = io.BytesIO()
            np.save(buffer, embedding, allow_pickle=False)
            prepared.append(
                (
                    index,
                    digest,
                    buffer.getvalue(),
                    angles[index] if angles is not None else None,
                )
            )
        now = utc_now()
        new_id = object_id or str(uuid4())
        try:
            with self.store.db:
                if object_id:
                    self.store.db.execute(
                        "UPDATE objects SET name=?, name_key=?, updated_at=? WHERE id=?",
                        (name, name.casefold(), now, new_id),
                    )
                    self.store.db.execute(
                        "DELETE FROM reference_views WHERE object_id=?", (new_id,)
                    )
                else:
                    self.store.db.execute(
                        "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                        (
                            new_id,
                            name,
                            name.casefold(),
                            self.signature,
                            self.encoder.embedding_dim,
                            now,
                            now,
                        ),
                    )
                self.store.db.executemany(
                    "INSERT INTO reference_views VALUES (?, ?, ?, ?, ?)",
                    [(new_id, *item) for item in prepared],
                )
        except sqlite3.IntegrityError as error:
            raise AssistantError(
                "OBJECT_NAME_EXISTS", "An active object already uses this name."
            ) from error
        return self.get(new_id)

    def rename(self, object_id: str, name: str) -> dict:
        self.get(object_id)
        name = label(name)
        try:
            with self.store.db:
                self.store.db.execute(
                    "UPDATE objects SET name=?, name_key=?, updated_at=? WHERE id=?",
                    (name, name.casefold(), utc_now(), object_id),
                )
        except sqlite3.IntegrityError as error:
            raise AssistantError(
                "OBJECT_NAME_EXISTS", "An active object already uses this name."
            ) from error
        return self.get(object_id)

    def archive(self, object_id: str) -> dict:
        self.get(object_id)
        now = utc_now()
        with self.store.db:
            self.store.db.execute(
                "UPDATE objects SET archived_at=?, updated_at=? WHERE id=?",
                (now, now, object_id),
            )
        return self.get(object_id, include_archived=True)

    def memory_bank(self, *, mode: str = "replay") -> ObjectMemoryBank:
        """Restore compatible objects into the existing search/verifier interface."""
        if mode not in {"synthetic", "replay", "physical"}:
            raise AssistantError(
                "INVALID_MODE", "Choose synthetic, replay, or physical evidence."
            )
        bank = ObjectMemoryBank(
            self.encoder, self.settings.perception, self.settings.planner
        )
        for record in self.list():
            self._compatible(record)
            refs = self.store.db.execute(
                "SELECT * FROM reference_views WHERE object_id=? ORDER BY ordinal",
                (record["id"],),
            ).fetchall()
            counts = Counter(
                row["station"]
                for row in self.history(record["id"], limit=None)
                if row["mode"] == mode and self.effective_status(row) == "present"
            )
            restored = ObjectRecord(
                name=record["name"],
                prototypes=np.stack(
                    [
                        np.load(io.BytesIO(row["embedding"]), allow_pickle=False)
                        for row in refs
                    ]
                ),
                reference_crops=[
                    self.store.load_image(row["image_sha"]) for row in refs
                ],
                view_angles_deg=[row["angle_deg"] for row in refs],
                station_hit_counts=dict(counts),
            )
            bank.restore_record(restored)
        return bank

    def match(self, image: np.ndarray) -> list[dict]:
        # Validate without asserting that an appearance match is an observed fact.
        if image is None or image.size == 0:
            raise AssistantError(
                "INVALID_IMAGE", "A nonempty candidate crop is required."
            )
        bank = self.memory_bank()
        embedding = self.encoder.embed(image)
        results = []
        for record in self.list():
            result = asdict(bank.match_embedding(embedding, record["name"]))
            result.update(
                object_id=record["id"],
                decision="candidate_only",
                score_semantics="uncalibrated_heuristic_not_probability",
                encoder_signature=self.signature,
            )
            results.append(result)
        return sorted(results, key=lambda item: item["heuristic_score"], reverse=True)

    def observe(
        self,
        object_id: str,
        station: str,
        assertion: str,
        image: np.ndarray,
        captured_at: str,
        *,
        quality: float = 1.0,
        visibility: float = 1.0,
        source: str = "operator",
        mode: str = "replay",
        provenance: dict | None = None,
        commit: bool = True,
    ) -> dict:
        self.get(object_id)
        station = label(station)
        if assertion not in {"present", "absent", "unknown"}:
            raise AssistantError(
                "INVALID_ASSERTION", "Use present, absent, or unknown."
            )
        if mode not in {"synthetic", "replay", "physical"} or source not in {
            "operator",
            "verifier",
            "synthetic",
        }:
            raise AssistantError(
                "INVALID_PROVENANCE", "Unsupported observation mode or source."
            )
        captured_at = timestamp(captured_at)
        recorded_at = utc_now()
        if captured_at > recorded_at:
            raise AssistantError(
                "FUTURE_OBSERVATION", "Capture time cannot be in the future."
            )
        quality, visibility = unit_score(quality), unit_score(visibility)
        try:
            provenance_json = json.dumps(provenance or {}, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise AssistantError(
                "INVALID_PROVENANCE", "Evidence metadata must be finite JSON."
            ) from error
        digest = self.store.save_image(image)
        observation_id = str(uuid4())
        if not commit and not self.store.db.in_transaction:
            raise AssistantError(
                "TRANSACTION_REQUIRED", "An outer transaction is required."
            )
        with self.store.db if commit else nullcontext():
            self.store.db.execute(
                "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    observation_id,
                    object_id,
                    station,
                    assertion,
                    captured_at,
                    recorded_at,
                    digest,
                    quality,
                    visibility,
                    source,
                    mode,
                    provenance_json,
                ),
            )
        return self.observation(observation_id)

    def observation(self, observation_id: str) -> dict:
        row = self.store.db.execute(
            "SELECT * FROM observations WHERE id=?", (observation_id,)
        ).fetchone()
        if row is None:
            raise AssistantError("OBSERVATION_NOT_FOUND", "Observation does not exist.")
        return self._observation_record(row)

    @staticmethod
    def _observation_record(row) -> dict:
        result = dict(row)
        result["provenance"] = json.loads(result.pop("provenance_json"))
        return result

    def effective_status(self, observation: dict) -> str:
        cfg = self.settings.assistant
        if (
            observation["quality"] < cfg.minimum_quality
            or observation["visibility"] < cfg.minimum_visibility
        ):
            return "unknown"
        return observation["assertion"]

    def history(self, object_id: str, *, limit: int | None = None) -> list[dict]:
        self.get(object_id, include_archived=True)
        if limit is not None and limit <= 0:
            raise AssistantError("INVALID_LIMIT", "History limit must be positive.")
        sql = "SELECT * FROM observations WHERE object_id=? ORDER BY captured_at DESC, recorded_at DESC, id"
        parameters: tuple = (object_id,)
        if limit is not None:
            sql += " LIMIT ?"
            parameters += (limit,)
        return [
            self._observation_record(row)
            for row in self.store.db.execute(sql, parameters)
        ]

    def last_seen(self, object_id: str, *, mode: str = "replay") -> dict:
        if mode not in {"synthetic", "replay", "physical"}:
            raise AssistantError(
                "INVALID_MODE", "Choose synthetic, replay, or physical evidence."
            )
        history = [row for row in self.history(object_id) if row["mode"] == mode]
        sighting = next(
            (row for row in history if self.effective_status(row) == "present"), None
        )
        return {
            "object_id": object_id,
            "mode": mode,
            "last_seen": sighting,
            "latest_observation": history[0] if history else None,
            "meaning": "historical_sighting_not_current_location",
        }
