"""Offline lifecycle/failure tests. Model doubles do not establish model quality."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import json
import time

import numpy as np
import pytest

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.memory_budget import reserve_call
from teach_and_find.storage import AssistantError, EvidenceStore
from teach_and_find.tracking_service import (
    TrackingService,
    frame_record,
    mask_bytes,
    save_mask,
)
from teach_and_find.tracking_worker import TrackingRunner


@pytest.fixture
def cfg(tmp_path):
    settings = Settings()
    return replace(
        settings,
        assistant=replace(settings.assistant, data_dir=str(tmp_path)),
        tracking=replace(settings.tracking, enabled=True),
    )


def frame(name="anchor"):
    return CameraFrame(
        np.full((48, 64, 3), 80, np.uint8),
        name,
        datetime.now(timezone.utc).isoformat(),
        time.monotonic(),
        0,
        True,
        {"camera_id": "explicit-offline-fixture", "session_id": "test-session"},
    )


def ready(store):
    with store.db:
        store.db.execute(
            "INSERT OR REPLACE INTO tracking_worker VALUES(1,?,?,?,?)",
            (0, time.time(), "ready", "null"),
        )


def test_missing_worker_owner_mode_revision_and_invalid_prompts(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        svc = TrackingService(store, cfg)
        with pytest.raises(AssistantError) as exc:
            svc.pin(frame(), "synthetic", "owner", "pin")
        assert exc.value.code == "TRACKING_WORKER_UNAVAILABLE"
        assert (
            store.db.execute("SELECT COUNT(*) FROM tracking_sessions").fetchone()[0]
            == 0
        )
        ready(store)
        anchor = frame()
        selected = svc.pin(anchor, "synthetic", "owner", "pin")
        assert svc.pin(anchor, "synthetic", "owner", "pin")["id"] == selected["id"]
        with pytest.raises(AssistantError) as exc:
            svc.stop(selected["id"], "synthetic", "other-owner")
        assert exc.value.code == "TRACKING_OWNERSHIP"
        with pytest.raises(AssistantError):
            svc.get(selected["id"], "physical")
        with pytest.raises(AssistantError) as exc:
            svc.prompt(selected["id"], "synthetic", "owner", 0, [[64, 20]], [1], None)
        assert exc.value.code == "PROMPT_INVALID"
        prompted = svc.prompt(
            selected["id"], "synthetic", "owner", 0, [[20, 20]], [1], None
        )
        assert prompted["revision"] == 1
        with pytest.raises(AssistantError) as exc:
            svc.prompt(selected["id"], "synthetic", "owner", 0, [[21, 20]], [1], None)
        assert exc.value.code == "TRACKING_REVISION_CONFLICT"


def test_stop_during_upstream_preview_discards_late_publication(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        ready(store)
        svc = TrackingService(store, cfg)
        selected = svc.pin(frame(), "synthetic", "owner", "pin")
        svc.prompt(selected["id"], "synthetic", "owner", 0, [[20, 20]], [1], None)

        class ExplicitTestDouble:
            provenance = {"source": "offline_orchestration_test_double"}

            def preview(self, image, prompt):
                svc.stop(selected["id"], "synthetic", "owner")
                return [(np.ones(image.shape[:2], np.uint8), 0.5)], 0.01

        TrackingRunner(cfg, ExplicitTestDouble()).tick(store)
        result = svc.get(selected["id"], "synthetic")
        assert result["status"] == "stopped" and result["generation"] == 2
        assert result["preview"] is None and result["latest"] is None
        assert (
            store.db.execute(
                "SELECT COUNT(*) FROM tracking_events WHERE kind='preview_discarded'"
            ).fetchone()[0]
            == 1
        )


def test_stop_during_model_step_does_not_publish_or_resurrect(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        ready(store)
        svc = TrackingService(store, cfg)
        selected = svc.pin(frame(), "synthetic", "owner", "pin")
        mask = np.ones((48, 64), np.uint8)
        preview = {"selected": 0, "candidates": [{"mask_sha": save_mask(store, mask)}]}
        with store.db:
            store.db.execute(
                "UPDATE tracking_sessions SET status='preview_ready',preview_json=? WHERE id=?",
                (json.dumps(preview), selected["id"]),
            )
        svc.start(selected["id"], "synthetic", "owner", 0, 0)

        class ExplicitTestDouble:
            def reset(self):
                pass

            def step(self, image, seed):
                svc.stop(selected["id"], "synthetic", "owner")
                return mask, 0.01

        TrackingRunner(cfg, ExplicitTestDouble()).tick(store)
        assert svc.get(selected["id"], "synthetic")["status"] == "stopped"
        assert (
            store.db.execute("SELECT COUNT(*) FROM tracking_observations").fetchone()[0]
            == 0
        )


def test_mask_corruption_fails_without_replacement(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        digest = save_mask(store, np.ones((10, 10), np.uint8))
        (store.root / "tracking-masks" / f"{digest}.png").write_bytes(b"corrupt")
        with pytest.raises(AssistantError) as exc:
            mask_bytes(store, digest)
        assert exc.value.code == "TRACKING_MASK_CORRUPT"
        bad = replace(frame(), freshness_verified=False)
        with pytest.raises(AssistantError):
            frame_record(store, bad)


def test_paid_attempt_cap_is_global_concurrent_and_persistent(tmp_path):
    cfg = replace(
        Settings().memory,
        global_call_budget_file=str(tmp_path / "paid.json"),
        global_call_budget=15,
    )

    def attempt(_):
        try:
            reserve_call(cfg)
            return True
        except AssistantError as exc:
            assert exc.code == "MODEL_GLOBAL_BUDGET_EXHAUSTED"
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(attempt, range(35))) == 15
    assert json.loads((tmp_path / "paid.json").read_text())["attempts"] == 15
    with pytest.raises(AssistantError) as exc:
        reserve_call(cfg)
    assert exc.value.code == "MODEL_GLOBAL_BUDGET_EXHAUSTED"
    with pytest.raises(AssistantError) as exc:
        reserve_call(replace(cfg, global_call_budget=16))
    assert exc.value.code == "MODEL_GLOBAL_BUDGET_CONFLICT"


def test_preview_bytes_cannot_exceed_session_budget(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        source = frame()
        anchor_size = len(store.image_bytes(store.save_image(source.image)))
        cfg = replace(
            cfg, tracking=replace(cfg.tracking, evidence_limit_bytes=anchor_size + 1)
        )
        ready(store)
        svc = TrackingService(store, cfg)
        session = svc.pin(source, "synthetic", "owner", "pin")
        svc.prompt(session["id"], "synthetic", "owner", 0, [[20, 20]], [1], None)

        class ExplicitTestDouble:
            provenance = {"source": "offline_orchestration_test_double"}

            def preview(self, image, prompt):
                return [(np.ones(image.shape[:2], np.uint8), 0.5)], 0.01

        TrackingRunner(cfg, ExplicitTestDouble()).tick(store)
        result = svc.get(session["id"], "synthetic")
        assert result["status"] == "failed"
        assert result["error_code"] == "TRACKING_STORAGE_LIMIT"
        assert result["preview"] is None and result["latest"] is None
