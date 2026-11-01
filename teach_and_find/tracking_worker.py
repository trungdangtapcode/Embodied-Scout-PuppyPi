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
from teach_and_find.storage import AssistantError, EvidenceStore
from teach_and_find.tracking_service import (
    ACTIVE,
    TrackingService,
    mask_bytes,
    save_mask,
)


class TrackingRunner:
    def __init__(self, settings, models):
        self.settings = settings
        self.models = models
        self.identity = None
        self.sequence = -1
        self.previous_capture = None
        self.last_good = None
        self.catchup_started = None

    def tick(self, store):
        cfg = self.settings.tracking
        svc = TrackingService(store, self.settings)
        row = store.db.execute(
            "SELECT * FROM tracking_sessions WHERE status IN (?,?,?,?,?)", ACTIVE
        ).fetchone()
        if row is None:
            self.identity = None
            self.models.processor = None
            return
        sid = row["id"]
        now = time.time()
        if now > min(row["expires_at"], row["lease_until"]):
            svc.finish(sid, "failed", "TRACKING_EXPIRED")
            return
        if json.loads(row["profile_json"]) != asdict(cfg):
            svc.finish(sid, "failed", "TRACKING_PROFILE_MISMATCH")
            return
        if row["status"] == "preview_pending":
            anchor = json.loads(row["anchor_json"])
            masks, elapsed = self.models.preview(
                store.load_image(anchor["image_sha"]), json.loads(row["prompt_json"])
            )
            if not masks or any(
                m.shape != (anchor["height"], anchor["width"]) for m, _ in masks
            ):
                raise AssistantError(
                    "TRACKING_MASK_INVALID",
                    "Preview dimensions differ from the pinned source.",
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
            mask_size = sum(len(mask_bytes(store, c["mask_sha"])) for c in candidates)
            with store.db:
                changed = store.db.execute(
                    "UPDATE tracking_sessions SET status='preview_ready',preview_json=?,evidence_bytes=evidence_bytes+? WHERE id=? AND generation=? AND revision=? AND status='preview_pending' AND evidence_bytes+?<=?",
                    (
                        json.dumps(preview),
                        mask_size,
                        sid,
                        row["generation"],
                        row["revision"],
                        mask_size,
                        cfg.evidence_limit_bytes,
                    ),
                ).rowcount
                svc.event(
                    row,
                    "preview_completed" if changed else "preview_discarded",
                    {"elapsed_s": elapsed},
                )
            if not changed:
                current = svc.row(sid, row["mode"])
                if (
                    current["status"] == "preview_pending"
                    and current["generation"] == row["generation"]
                ):
                    svc.finish(sid, "failed", "TRACKING_STORAGE_LIMIT")
            return
        if row["status"] not in ("start_pending", "running"):
            return
        identity = (sid, row["generation"])
        if row["status"] == "start_pending":
            if self.identity != identity:
                self.models.reset()
                self.identity = identity
                self.sequence = -1
                self.previous_capture = None
                self.last_good = None
                self.catchup_started = now
            frame_row = store.db.execute(
                "SELECT * FROM tracking_frames WHERE session_id=? AND sequence=0",
                (sid,),
            ).fetchone()
            preview = json.loads(row["preview_json"])
            candidate = preview["candidates"][preview["selected"]]
            seed = (
                np.asarray(
                    Image.open(io.BytesIO(mask_bytes(store, candidate["mask_sha"])))
                )
                > 0
            ).astype(np.uint8)
            if not seed.any():
                raise AssistantError(
                    "TRACKING_EMPTY_SEED", "Actual model seed mask is empty."
                )
        else:
            if self.identity != identity:
                svc.finish(sid, "interrupted", "TRACKING_PROCESSOR_LOST")
                return
            frame_row = store.db.execute(
                "SELECT * FROM tracking_frames WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT 1",
                (sid, self.sequence),
            ).fetchone()
            seed = None
        if not frame_row:
            if (
                self.previous_capture is not None
                and now - self.previous_capture > cfg.max_frame_gap_s
            ):
                svc.finish(sid, "failed", "TRACKING_FRAME_GAP")
            return
        frame = json.loads(frame_row["record_json"])
        captured = frame["capture_unix_ms"] / 1000
        if (
            self.previous_capture is not None
            and not 0 < captured - self.previous_capture <= cfg.max_frame_gap_s
        ):
            svc.finish(sid, "failed", "TRACKING_FRAME_GAP")
            return
        began = time.time()
        mask, elapsed = self.models.step(store.load_image(frame["image_sha"]), seed)
        if mask.shape != (frame["height"], frame["width"]):
            raise AssistantError(
                "TRACKING_MASK_INVALID",
                "Output dimensions differ from the processed source.",
            )
        self.sequence = frame_row["sequence"]
        self.previous_capture = captured
        pixels = int(mask.sum())
        self.last_good = captured if pixels else self.last_good
        state = "tracked_unverified" if pixels else "uncertain"
        if (
            not pixels
            and self.last_good is not None
            and captured - self.last_good >= cfg.empty_grace_s
        ):
            svc.finish(sid, "failed", "TRACKING_LOST")
            return
        record = {
            **frame,
            "sequence": self.sequence,
            "generation": row["generation"],
            "mask_sha": save_mask(store, mask),
            "foreground_pixels": pixels,
            "observation_state": state,
            "inference_started_unix_ms": began * 1000,
            "inference_finished_unix_ms": time.time() * 1000,
            "step_s": elapsed,
            "mask_encoding": "binary_0_255_png_original_raster",
            "identity": "unverified",
            "source": "actual_original_cutie_inference",
        }
        ys, xs = np.where(mask > 0)
        record["xyxy"] = (
            [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
            if pixels
            else None
        )
        record["published_unix_ms"] = time.time() * 1000
        mask_size = len(mask_bytes(store, record["mask_sha"]))
        with store.db:
            current = store.db.execute(
                "SELECT status,generation,evidence_bytes FROM tracking_sessions WHERE id=?",
                (sid,),
            ).fetchone()
            if (
                current["status"] not in ("start_pending", "running")
                or current["generation"] != row["generation"]
            ):
                svc.event(row, "observation_discarded", {"sequence": self.sequence})
                return
            if current["evidence_bytes"] + mask_size > cfg.evidence_limit_bytes:
                svc.finish(sid, "failed", "TRACKING_STORAGE_LIMIT")
                return
            store.db.execute(
                "INSERT INTO tracking_observations VALUES(?,?,?,?)",
                (sid, row["generation"], self.sequence, json.dumps(record)),
            )
            store.db.execute(
                "UPDATE tracking_sessions SET status='running',evidence_bytes=evidence_bytes+? WHERE id=?",
                (mask_size, sid),
            )
        if (
            time.time() - captured > cfg.max_result_age_s
            and time.time() - self.catchup_started > cfg.max_catchup_s
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
