"""Durable target selection, bounded frame feed and generation-guarded evidence.

No model is imported here. Custom lifecycle/empty-mask rules are operational
heuristics; they do not establish target presence or physical identity.
"""

from dataclasses import asdict
from datetime import datetime
import hashlib
import io
import json
import queue
import threading
import time
from uuid import uuid4

import numpy as np
from PIL import Image

from teach_and_find.config import Settings
from teach_and_find.storage import AssistantError, EvidenceStore

ACTIVE = ("selecting", "preview_pending", "preview_ready", "start_pending", "running")


def owner_key(owner):
    return hashlib.sha256(owner.encode()).hexdigest()


def frame_record(store, frame):
    persisted_started = time.time() * 1000
    provenance = dict(frame.provenance)
    camera = provenance.get("camera_id"), provenance.get("session_id")
    if not all(camera) or not frame.freshness_verified:
        raise AssistantError(
            "TRACKING_CAMERA_INVALID", "An identified timestamped camera is required."
        )
    return {
        "frame_id": frame.frame_id,
        "image_sha": store.save_image(frame.image),
        "captured_at": frame.captured_at,
        "capture_unix_ms": datetime.fromisoformat(frame.captured_at).timestamp() * 1000,
        "persistence_started_unix_ms": persisted_started,
        "width": int(frame.image.shape[1]),
        "height": int(frame.image.shape[0]),
        "provenance": provenance,
    }


def save_mask(store, mask):
    if mask.dtype != np.uint8 or mask.ndim != 2 or not np.isin(mask, [0, 1]).all():
        raise AssistantError(
            "TRACKING_MASK_INVALID", "Expected a binary HW uint8 model mask."
        )
    output = io.BytesIO()
    Image.fromarray(mask * 255).save(output, format="PNG")
    payload = output.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    directory = store.root / "tracking-masks"
    directory.mkdir(exist_ok=True)
    path = directory / f"{digest}.png"
    if not path.exists():
        temporary = directory / f"{digest}.{uuid4().hex}.tmp"
        temporary.write_bytes(payload)
        temporary.replace(path)
    return digest


def mask_bytes(store, digest):
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise AssistantError("TRACKING_MASK_INVALID", "Invalid mask digest.")
    path = store.root / "tracking-masks" / f"{digest}.png"
    if not path.exists():
        raise AssistantError("TRACKING_MASK_NOT_FOUND", "Saved model mask is missing.")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise AssistantError(
            "TRACKING_MASK_CORRUPT", "Saved model mask digest mismatch."
        )
    return payload


class TrackingService:
    def __init__(self, store: EvidenceStore, settings: Settings):
        self.store, self.settings = store, settings
        self.cfg = settings.tracking
        self.store.db.execute("PRAGMA busy_timeout=100")

    def worker(self):
        row = self.store.db.execute(
            "SELECT * FROM tracking_worker WHERE id=1"
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["alive"] = (
            time.time() - row["seen_at"] <= self.cfg.worker_stale_s
            and row["status"] == "ready"
        )
        return result

    def require_ready(self):
        if not self.cfg.enabled:
            raise AssistantError(
                "TRACKING_DISABLED", "Tracking is disabled; no substitute."
            )
        if not (self.worker() or {}).get("alive"):
            raise AssistantError(
                "TRACKING_WORKER_UNAVAILABLE",
                "The required tracking worker is not ready.",
            )

    def row(self, sid, mode, owner=None):
        row = self.store.db.execute(
            "SELECT * FROM tracking_sessions WHERE id=? AND mode=?", (sid, mode)
        ).fetchone()
        if not row:
            raise AssistantError(
                "TRACKING_SESSION_NOT_FOUND", "No tracking session in this input mode."
            )
        if owner is not None and row["owner"] != owner_key(owner):
            raise AssistantError(
                "TRACKING_OWNERSHIP", "This device does not own the tracking session."
            )
        return row

    def event(self, row, kind, record):
        self.store.db.execute(
            "INSERT INTO tracking_events(session_id,generation,at,kind,record_json) VALUES(?,?,?,?,?)",
            (row["id"], row["generation"], time.time(), kind, json.dumps(record)),
        )

    def finish(self, sid, status, code=None, error=None):
        with self.store.db:
            row = self.store.db.execute(
                "SELECT * FROM tracking_sessions WHERE id=?", (sid,)
            ).fetchone()
            if row and row["status"] in ACTIVE:
                self.store.db.execute(
                    "UPDATE tracking_sessions SET status=?,generation=generation+1,error_code=?,error_json=? WHERE id=?",
                    (status, code, json.dumps(error) if error else None, sid),
                )
                self.event(row, status, {"code": code, "error": error})

    def pin(self, frame, mode, owner, key):
        self.require_ready()
        existing = self.store.db.execute(
            "SELECT * FROM tracking_sessions WHERE owner=? AND mode=? AND request_key=?",
            (owner_key(owner), mode, key),
        ).fetchone()
        if existing:
            if json.loads(existing["anchor_json"])["frame_id"] != frame.frame_id:
                raise AssistantError(
                    "IDEMPOTENCY_CONFLICT",
                    "Request key belongs to a different displayed frame.",
                )
            return self.get(existing["id"], mode)
        if frame.age() > self.settings.mobile.max_frame_age_s:
            raise AssistantError("STALE_FRAME", "Select a fresh displayed frame.")
        now = time.time()
        sid = str(uuid4())
        anchor = frame_record(self.store, frame)
        anchor_size = len(self.store.image_bytes(anchor["image_sha"]))
        if anchor_size > self.cfg.evidence_limit_bytes:
            raise AssistantError(
                "TRACKING_STORAGE_LIMIT", "Anchor exceeds the session evidence budget."
            )
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            active = self.store.db.execute(
                "SELECT id FROM tracking_sessions WHERE status IN (?,?,?,?,?)", ACTIVE
            ).fetchone()
            if active:
                raise AssistantError(
                    "TRACKING_CAPACITY", "Stop the current target session first."
                )
            self.store.db.execute(
                "INSERT INTO tracking_sessions(id,owner,mode,request_key,generation,revision,status,created_at,expires_at,lease_until,anchor_json,profile_json) VALUES(?,?,?,?,1,0,?,?,?,?,?,?)",
                (
                    sid,
                    owner_key(owner),
                    mode,
                    key,
                    "selecting",
                    now,
                    now + self.cfg.anchor_lifetime_s,
                    now + self.cfg.owner_lease_s,
                    json.dumps(anchor),
                    json.dumps(asdict(self.cfg)),
                ),
            )
            self.store.db.execute(
                "INSERT INTO tracking_frames VALUES(?,?,?,?)",
                (sid, 0, frame.frame_id, json.dumps(anchor)),
            )
            row = self.row(sid, mode)
            self.store.db.execute(
                "UPDATE tracking_sessions SET evidence_bytes=? WHERE id=?",
                (anchor_size, sid),
            )
            self.event(row, "anchor_pinned", {"image_sha": anchor["image_sha"]})
        return self.get(sid, mode)

    def prompt(self, sid, mode, owner, expected_revision, points, labels, box):
        self.require_ready()
        row = self.row(sid, mode, owner)
        if (
            row["status"] not in ("selecting", "preview_ready")
            or row["revision"] != expected_revision
        ):
            raise AssistantError(
                "TRACKING_REVISION_CONFLICT",
                "Selection revision changed; refresh before prompting.",
            )
        if time.time() > row["expires_at"]:
            self.finish(sid, "failed", "ANCHOR_EXPIRED")
            raise AssistantError(
                "ANCHOR_EXPIRED", "Selection expired. Choose a new current frame."
            )
        anchor = json.loads(row["anchor_json"])
        w, h = anchor["width"], anchor["height"]
        if (
            not points
            and box is None
            or len(points) != len(labels)
            or any(v not in (0, 1) for v in labels)
        ):
            raise AssistantError(
                "PROMPT_INVALID", "Supply foreground/background points or a box."
            )
        if any(not 0 <= x < w or not 0 <= y < h for x, y in points):
            raise AssistantError(
                "PROMPT_INVALID", "Prompt points must be inside the source image."
            )
        if box is not None and not (
            0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h
        ):
            raise AssistantError(
                "PROMPT_INVALID", "Box must have positive area inside the source image."
            )
        prompt = {
            "points": points,
            "labels": labels,
            "box": box,
            "source": "operator_prompt_not_inferred_identity",
        }
        with self.store.db:
            count = self.store.db.execute(
                "UPDATE tracking_sessions SET prompt_json=?,status='preview_pending',revision=revision+1,preview_json=NULL WHERE id=? AND revision=? AND status IN ('selecting','preview_ready')",
                (json.dumps(prompt), sid, expected_revision),
            ).rowcount
            if count != 1:
                raise AssistantError(
                    "TRACKING_REVISION_CONFLICT", "Selection revision changed."
                )
            self.event(row, "prompt_submitted", prompt)
        return self.get(sid, mode)

    def start(self, sid, mode, owner, revision, candidate):
        self.require_ready()
        row = self.row(sid, mode, owner)
        if row["status"] != "preview_ready" or row["revision"] != revision:
            raise AssistantError(
                "TRACKING_REVISION_CONFLICT",
                "Approve an actual current model preview first.",
            )
        if time.time() > row["expires_at"]:
            self.finish(sid, "failed", "ANCHOR_EXPIRED")
            raise AssistantError(
                "ANCHOR_EXPIRED", "Preview expired; select a current frame."
            )
        preview = json.loads(row["preview_json"])
        if not 0 <= candidate < len(preview["candidates"]):
            raise AssistantError(
                "PROMPT_INVALID", "Choose an actual returned model mask."
            )
        preview["selected"] = candidate
        with self.store.db:
            changed = self.store.db.execute(
                "UPDATE tracking_sessions SET status='start_pending',preview_json=?,started_at=?,expires_at=? WHERE id=? AND revision=? AND status='preview_ready'",
                (
                    json.dumps(preview),
                    time.time(),
                    time.time() + self.cfg.session_lifetime_s,
                    sid,
                    revision,
                ),
            ).rowcount
            if changed != 1:
                raise AssistantError(
                    "TRACKING_REVISION_CONFLICT", "Preview changed before start."
                )
            self.event(
                row,
                "target_approved",
                {
                    "candidate": candidate,
                    "source": "operator_selected_extent_not_identity",
                },
            )
        return self.get(sid, mode)

    def stop(self, sid, mode, owner):
        self.row(sid, mode, owner)
        self.finish(sid, "stopped", "OPERATOR_STOP")
        return self.get(sid, mode)

    def get(self, sid, mode, after=-1):
        row = self.row(sid, mode)
        records = [
            json.loads(r[0])
            for r in self.store.db.execute(
                "SELECT record_json FROM tracking_observations WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT 120",
                (sid, after),
            )
        ]
        latest = self.store.db.execute(
            "SELECT record_json FROM tracking_observations WHERE session_id=? ORDER BY sequence DESC LIMIT 1",
            (sid,),
        ).fetchone()
        latest = json.loads(latest[0]) if latest else None
        if latest:
            latest["display_age_s"] = time.time() - latest["capture_unix_ms"] / 1000
            latest["stale"] = (
                latest["display_age_s"] > self.cfg.max_result_age_s
                or row["status"] != "running"
            )
        return {
            k: row[k]
            for k in (
                "id",
                "mode",
                "generation",
                "revision",
                "status",
                "created_at",
                "expires_at",
                "started_at",
                "error_code",
                "dropped_frames",
                "evidence_bytes",
            )
        } | {
            "anchor": json.loads(row["anchor_json"]),
            "preview": json.loads(row["preview_json"]) if row["preview_json"] else None,
            "latest": latest,
            "observations": records,
            "server_unix_ms": time.time() * 1000,
            "method": "original_sam21_tiny_cutie_base_megamodel_identity_unverified",
            "health_method": "custom_empty_mask_and_time_gap_rules_not_a_learned_absence_model",
        }

    def overview(self, mode):
        rows = self.store.db.execute(
            "SELECT id FROM tracking_sessions WHERE mode=? ORDER BY created_at DESC LIMIT 5",
            (mode,),
        ).fetchall()
        return {
            "enabled": self.cfg.enabled,
            "worker": self.worker(),
            "device": self.cfg.device,
            "offer_hz": self.cfg.offer_hz,
            "sessions": [self.get(r[0], mode, 10**18) for r in rows],
        }


class TrackingFeed:
    """The camera offers nonblockingly; PNG/SQLite work runs off its thread."""

    def __init__(self, settings):
        self.settings = settings
        self.pending = queue.Queue(maxsize=settings.tracking.producer_capacity)
        self.closed = threading.Event()
        self.thread = None
        self.dropped = 0
        self.last_offer = 0.0

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def offer(self, frame):
        now = time.monotonic()
        if now - self.last_offer < 1 / self.settings.tracking.offer_hz:
            return
        self.last_offer = now
        try:
            self.pending.put_nowait(frame)
        except queue.Full:
            self.dropped += 1

    def loop(self):
        while not self.closed.is_set():
            try:
                frame = self.pending.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                with EvidenceStore(self.settings.assistant.data_dir) as store:
                    svc = TrackingService(store, self.settings)
                    row = store.db.execute(
                        "SELECT * FROM tracking_sessions WHERE status IN (?,?,?,?,?)",
                        ACTIVE,
                    ).fetchone()
                    if not row:
                        continue
                    if not (svc.worker() or {}).get("alive"):
                        svc.finish(row["id"], "failed", "TRACKING_WORKER_UNAVAILABLE")
                        continue
                    if time.time() > min(row["expires_at"], row["lease_until"]):
                        svc.finish(row["id"], "failed", "TRACKING_EXPIRED")
                        continue
                    anchor = json.loads(row["anchor_json"])
                    p = frame.provenance
                    if (p.get("camera_id"), p.get("session_id")) != (
                        anchor["provenance"]["camera_id"],
                        anchor["provenance"]["session_id"],
                    ):
                        svc.finish(row["id"], "failed", "CAMERA_SESSION_CHANGED")
                        continue
                    if frame.captured_at <= anchor["captured_at"]:
                        continue
                    if store.db.execute(
                        "SELECT 1 FROM tracking_frames WHERE session_id=? AND frame_id=?",
                        (row["id"], frame.frame_id),
                    ).fetchone():
                        continue
                    record = frame_record(store, frame)
                    size = len(store.image_bytes(record["image_sha"]))
                    if (
                        row["evidence_bytes"] + size
                        > self.settings.tracking.evidence_limit_bytes
                    ):
                        svc.finish(row["id"], "failed", "TRACKING_STORAGE_LIMIT")
                        continue
                    with store.db:
                        seq = store.db.execute(
                            "SELECT COALESCE(MAX(sequence),0)+1 FROM tracking_frames WHERE session_id=?",
                            (row["id"],),
                        ).fetchone()[0]
                        store.db.execute(
                            "INSERT INTO tracking_frames VALUES(?,?,?,?)",
                            (row["id"], seq, frame.frame_id, json.dumps(record)),
                        )
                        store.db.execute(
                            "UPDATE tracking_sessions SET evidence_bytes=evidence_bytes+?,dropped_frames=dropped_frames+? WHERE id=?",
                            (size, self.dropped, row["id"]),
                        )
                        self.dropped = 0
                        store.db.execute(
                            "DELETE FROM tracking_frames WHERE session_id=? AND sequence>0 AND sequence<?",
                            (row["id"], seq - self.settings.tracking.frame_limit + 1),
                        )
            except Exception as error:
                # A writer failure never blocks capture or fabricates an observation.
                try:
                    with EvidenceStore(self.settings.assistant.data_dir) as store:
                        active = store.db.execute(
                            "SELECT id FROM tracking_sessions WHERE status IN (?,?,?,?,?)",
                            ACTIVE,
                        ).fetchone()
                        if active:
                            TrackingService(store, self.settings).finish(
                                active[0],
                                "failed",
                                "TRACKING_FEED_FAILED",
                                {"type": type(error).__name__},
                            )
                except Exception:
                    pass

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=3)
