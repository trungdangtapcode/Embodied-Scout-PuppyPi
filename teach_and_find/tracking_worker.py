"""One persistent original-model processor; no model work in the app process."""

from dataclasses import asdict
import fcntl
import io
import json
import os
from pathlib import Path
import signal
import socket
import threading
import time

import numpy as np
from PIL import Image

from teach_and_find.config import Settings
from teach_and_find.tracking_frames import FrameInbox
from teach_and_find.tracking_schedule import ScheduledFrame
from teach_and_find.storage import AssistantError, EvidenceStore
from teach_and_find.tracking_service import (
    ACTIVE,
    TrackingService,
    mask_bytes,
    save_mask,
)


class TrackingRunner:
    """Single-owner state machine; scheduler/storage/model responsibilities differ."""

    def __init__(self, settings, models):
        self.settings, self.models = settings, models
        self.identity = None
        self.sequence = -1
        self.previous_capture = None
        self.last_good = None
        self.catchup_started = None

    def tick(self, store):
        svc = TrackingService(store, self.settings)
        row = store.db.execute(
            "SELECT * FROM tracking_sessions WHERE status IN (?,?,?,?,?)", ACTIVE
        ).fetchone()
        if row is None:
            self.identity = None
            self.models.processor = None
            return
        cfg = self.settings.tracking
        if time.time() > min(row["expires_at"], row["lease_until"]):
            svc.finish(row["id"], "failed", "TRACKING_EXPIRED")
        elif json.loads(row["profile_json"]) != asdict(cfg):
            svc.finish(row["id"], "failed", "TRACKING_PROFILE_MISMATCH")
        elif (
            cfg.profile_version != 2
            or FrameInbox(store, cfg).snapshot(row["id"]) is None
        ):
            svc.finish(row["id"], "failed", "TRACKING_PROFILE_UNSUPPORTED")
        elif row["status"] == "preview_pending":
            self._preview(store, svc, row)
        elif row["status"] == "start_pending":
            self._initialize(store, svc, row)
        elif row["status"] == "running":
            self._advance(store, svc, row)

    def _preview(self, store, svc, row):
        anchor = json.loads(row["anchor_json"])
        masks, elapsed = self.models.preview(
            store.load_image(anchor["image_sha"]), json.loads(row["prompt_json"])
        )
        if not masks or any(
            m.shape != (anchor["height"], anchor["width"]) or not np.isfinite(score)
            for m, score in masks
        ):
            raise AssistantError(
                "TRACKING_MASK_INVALID", "Invalid preview shape or score."
            )
        candidates = [
            {
                "mask_sha": save_mask(store, m),
                "model_mask_quality_score": score,
                "foreground_pixels": int(m.sum()),
            }
            for m, score in masks
        ]
        preview = {
            "candidates": candidates,
            "selected": int(
                np.argmax([c["model_mask_quality_score"] for c in candidates])
            ),
            "elapsed_s": elapsed,
            "provenance": self.models.provenance,
            "anchor_image_sha": anchor["image_sha"],
        }
        size = sum(len(mask_bytes(store, c["mask_sha"])) for c in candidates)
        with store.db:
            changed = store.db.execute(
                "UPDATE tracking_sessions SET status='preview_ready',preview_json=?,evidence_bytes=evidence_bytes+? WHERE id=? AND generation=? AND revision=? AND status='preview_pending' AND evidence_bytes+?<=?",
                (
                    json.dumps(preview),
                    size,
                    row["id"],
                    row["generation"],
                    row["revision"],
                    size,
                    svc.cfg.evidence_limit_bytes,
                ),
            ).rowcount
            svc.event(
                row,
                "preview_completed" if changed else "preview_discarded",
                {"elapsed_s": elapsed},
            )
        if not changed:
            current = svc.row(row["id"], row["mode"])
            if (
                current["status"] == "preview_pending"
                and current["generation"] == row["generation"]
            ):
                svc.finish(row["id"], "failed", "TRACKING_STORAGE_LIMIT")

    def _initialize(self, store, svc, row):
        identity = (row["id"], row["generation"])
        if self.identity != identity:
            self.models.reset()
            self.identity = identity
            self.sequence = -1
            self.previous_capture = self.last_good = None
            self.catchup_started = time.time()
        source = store.db.execute(
            "SELECT record_json FROM tracking_frames WHERE session_id=? AND sequence=0",
            (row["id"],),
        ).fetchone()
        if source is None:
            raise AssistantError(
                "TRACKING_ANCHOR_MISSING", "The approved source is unavailable."
            )
        preview = json.loads(row["preview_json"])
        candidate = preview["candidates"][preview["selected"]]
        seed = (
            np.asarray(Image.open(io.BytesIO(mask_bytes(store, candidate["mask_sha"]))))
            > 0
        ).astype(np.uint8)
        if not seed.any():
            raise AssistantError(
                "TRACKING_EMPTY_SEED", "Actual model seed mask is empty."
            )
        head = store.db.execute(
            "SELECT MAX(sequence) FROM tracking_frames WHERE session_id=?", (row["id"],)
        ).fetchone()[0]
        selected = ScheduledFrame(0, json.loads(source[0]), head == 0, 0, "bootstrap")
        self._infer(store, svc, row, selected, seed)

    def _advance(self, store, svc, row):
        if self.identity != (row["id"], row["generation"]):
            svc.finish(row["id"], "interrupted", "TRACKING_PROCESSOR_LOST")
            return
        inbox = FrameInbox(store, svc.cfg)
        state = inbox.snapshot(row["id"])
        if (
            state["phase"] == "bootstrap"
            and time.time() - self.catchup_started > svc.cfg.max_catchup_s
        ):
            svc.finish(row["id"], "failed", "TRACKING_CATCHUP_EXCEEDED")
            return
        selected = inbox.claim(
            row["id"], row["generation"], self.sequence, self.previous_capture
        )
        if selected is not None:
            self._infer(store, svc, row, selected, None)

    def _infer(self, store, svc, row, selected, seed):
        frame = selected.record
        captured = frame["capture_unix_ms"] / 1000
        began = time.time()
        mask, elapsed = self.models.step(store.load_image(frame["image_sha"]), seed)
        if mask.shape != (frame["height"], frame["width"]):
            raise AssistantError(
                "TRACKING_MASK_INVALID",
                "Output dimensions differ from the processed source.",
            )
        gap = (
            None if self.previous_capture is None else captured - self.previous_capture
        )
        self.sequence, self.previous_capture = selected.sequence, captured
        pixels = int(mask.sum())
        self.last_good = captured if pixels else self.last_good
        if (
            not pixels
            and self.last_good is not None
            and captured - self.last_good >= svc.cfg.empty_grace_s
        ):
            svc.finish(row["id"], "failed", "TRACKING_LOST")
            return
        record = {
            **frame,
            "sequence": selected.sequence,
            "generation": row["generation"],
            "mask_sha": save_mask(store, mask),
            "foreground_pixels": pixels,
            "observation_state": "tracked_unverified" if pixels else "uncertain",
            "inference_started_unix_ms": began * 1000,
            "inference_finished_unix_ms": time.time() * 1000,
            "step_s": elapsed,
            "mask_encoding": "binary_0_255_png_original_raster",
            "identity": "unverified",
            "source": "actual_original_cutie_inference",
            "scheduling_policy": "bounded_bootstrap_then_latest_pending_v2",
            "stream_phase_at_claim": selected.phase,
            "skipped_admitted_frames": selected.skipped,
            "capture_gap_s": gap,
        }
        ys, xs = np.where(mask > 0)
        record["xyxy"] = (
            [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
            if pixels
            else None
        )
        self._publish(store, svc, row, selected, record)

    def _publish(self, store, svc, row, selected, record):
        sid = row["id"]
        size = len(mask_bytes(store, record["mask_sha"]))
        record["published_unix_ms"] = time.time() * 1000
        fresh = (
            time.time() - record["capture_unix_ms"] / 1000 <= svc.cfg.max_result_age_s
        )
        with store.db:
            # Take the writer lock before the check; stop can never interleave
            # between a stale generation check and an observation commit.
            store.db.execute("BEGIN IMMEDIATE")
            current = store.db.execute(
                "SELECT status,generation,evidence_bytes FROM tracking_sessions WHERE id=?",
                (sid,),
            ).fetchone()
            if (
                current["status"] not in ("start_pending", "running")
                or current["generation"] != row["generation"]
            ):
                svc.event(row, "observation_discarded", {"sequence": selected.sequence})
                return
            if current["evidence_bytes"] + size > svc.cfg.evidence_limit_bytes:
                svc.finish(sid, "failed", "TRACKING_STORAGE_LIMIT")
                return
            record["stream_phase_after"] = FrameInbox(store, svc.cfg).completed(
                sid, selected.sequence, selected.was_head, fresh
            )
            store.db.execute(
                "INSERT INTO tracking_observations VALUES(?,?,?,?)",
                (sid, row["generation"], selected.sequence, json.dumps(record)),
            )
            store.db.execute(
                "UPDATE tracking_sessions SET status='running',evidence_bytes=evidence_bytes+? WHERE id=?",
                (size, sid),
            )
        if selected.phase == "live" and not fresh:
            svc.finish(sid, "failed", "TRACKING_RESULT_STALE")
        elif (
            record["stream_phase_after"] == "bootstrap"
            and time.time() - self.catchup_started > svc.cfg.max_catchup_s
        ):
            svc.finish(sid, "failed", "TRACKING_CATCHUP_EXCEEDED")


def main():
    cfg = Settings()
    root = Path(cfg.assistant.data_dir)
    root.mkdir(parents=True, exist_ok=True)
    if not cfg.tracking.enabled:
        raise RuntimeError("Tracking is disabled.")
    stopped = threading.Event()
    status = {"value": "loading", "error": None}
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    with (root / "tracking-worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with EvidenceStore(root) as store:
            for r in store.db.execute(
                "SELECT id FROM tracking_sessions WHERE status IN (?,?,?,?,?)", ACTIVE
            ).fetchall():
                TrackingService(store, cfg).finish(
                    r[0], "interrupted", "TRACKING_WORKER_RESTARTED"
                )

        def heartbeat():
            while not stopped.is_set():
                try:
                    with EvidenceStore(root) as store, store.db:
                        store.db.execute(
                            "INSERT OR REPLACE INTO tracking_worker VALUES(1,?,?,?,?)",
                            (
                                os.getpid(),
                                time.time(),
                                status["value"],
                                json.dumps(status["error"]),
                            ),
                        )
                except Exception:
                    pass
                stopped.wait(cfg.tracking.heartbeat_s)

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            from teach_and_find.tracking_models import TrackingModels

            # Provisioning is separate; inference cannot perform network downloads.
            def reject_network(*args, **kwargs):
                raise RuntimeError("NETWORK_FORBIDDEN_IN_TRACKING_WORKER")

            socket.socket.connect = reject_network
            models = TrackingModels(cfg.tracking)
            runner = TrackingRunner(cfg, models)
            status["value"] = "ready"
            print("Tracking worker ready; original SAM 2.1 + Cutie.", flush=True)
            while not stopped.is_set():
                with EvidenceStore(root) as store:
                    try:
                        runner.tick(store)
                    except Exception as error:
                        r = store.db.execute(
                            "SELECT id FROM tracking_sessions WHERE status IN (?,?,?,?,?)",
                            ACTIVE,
                        ).fetchone()
                        if r:
                            TrackingService(store, cfg).finish(
                                r[0],
                                "failed",
                                getattr(error, "code", "TRACKING_INFERENCE_FAILED"),
                                {
                                    "type": type(error).__name__,
                                    "message": str(error)[:1000],
                                },
                            )
                stopped.wait(cfg.tracking.polling_s)
        except Exception as error:
            status["value"] = "failed"
            status["error"] = {
                "type": type(error).__name__,
                "message": str(error)[:1000],
            }
            with EvidenceStore(root) as store, store.db:
                store.db.execute(
                    "INSERT OR REPLACE INTO tracking_worker VALUES(1,?,?,?,?)",
                    (os.getpid(), time.time(), "failed", json.dumps(status["error"])),
                )
            raise
        finally:
            stopped.set()
            thread.join(timeout=3)
            with EvidenceStore(root) as store, store.db:
                for r in store.db.execute(
                    "SELECT id FROM tracking_sessions WHERE status IN (?,?,?,?,?)",
                    ACTIVE,
                ).fetchall():
                    TrackingService(store, cfg).finish(
                        r[0], "interrupted", "TRACKING_WORKER_STOPPED"
                    )
                if status["value"] != "failed":
                    store.db.execute(
                        "UPDATE tracking_worker SET status='stopped',seen_at=? WHERE id=1",
                        (time.time(),),
                    )


if __name__ == "__main__":
    main()
