"""Offline contract/failure tests. Injected adapter outputs are not model evidence."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import subprocess
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import build_library
from teach_and_find.memory_queue import dispatch, queue_for
from teach_and_find.memory_service import MemoryService
from teach_and_find.mobile.api import create_app
from teach_and_find.storage import AssistantError, EvidenceStore
from teach_and_find.vision_service import VisionService
from teach_and_find.vision_worker import execute_job
from teach_and_find.yoloe_adapter import verify_artifacts


@pytest.fixture
def cfg(tmp_path):
    c = Settings()
    return replace(
        c,
        assistant=replace(c.assistant, data_dir=str(tmp_path)),
        vision=replace(c.vision, enabled=True),
        memory=replace(c.memory, enabled=True),
        mobile=replace(c.mobile, pairing_token="offline-test"),
    )


def frames():
    now = datetime.now(timezone.utc)
    return [
        CameraFrame(
            np.full((80, 90, 3), 90 + i, np.uint8),
            f"f{i}",
            (now - timedelta(seconds=(3 - i) * 0.2)).isoformat(),
            time.monotonic(),
            0,
            True,
            {
                "camera_id": "offline-fixture",
                "session_id": "test-session",
                "capture_time_basis": "test_clock",
                "calibration_id": "test-calibration",
            },
        )
        for i in range(3)
    ]


def enroll(store, cfg):
    return build_library(store, cfg).teach("Reference input", [frames()[0].image])["id"]


def test_snapshot_retries_reference_changes_and_queue_isolation(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        oid = enroll(store, cfg)
        svc = VisionService(store, cfg)
        source = frames()
        job = svc.enqueue(source, [oid], "same-key", "synthetic")
        internal = svc.job(job["id"], "synthetic", internal=True)
        original = internal["payload"]["frames"][0]["image_sha"]
        source[0].image[:] = 0
        build_library(store, cfg).rename(oid, "Renamed after admission")
        assert svc.enqueue(source, [oid], "same-key", "synthetic")["id"] == job["id"]
        assert store.load_image(original)[0, 0, 0] == 90
        assert internal["payload"]["references"][0]["name"] == "Reference input"
        assert "embedding" not in str(internal["payload"])
        assert svc.overview("replay")["jobs"] == []
        assert MemoryService(store, cfg).overview("synthetic")["jobs"] == []
        with pytest.raises(AssistantError, match="different memory input"):
            svc.enqueue(source[-1:], ["other"], "same-key", "synthetic")
    with pytest.raises(ValueError, match="another inference queue"):
        dispatch(cfg, job["id"], "memory")
    dispatch(cfg, job["id"], "vision")
    dispatch(cfg, job["id"], "vision")
    assert queue_for(cfg, "vision").pending_count() == 1
    assert queue_for(cfg).pending_count() == 0


@pytest.mark.parametrize(
    "change,code",
    [
        (
            lambda fs: [
                fs[0],
                replace(
                    fs[1],
                    provenance={"camera_id": "other", "session_id": "test-session"},
                ),
            ],
            "VISION_CAMERA_MISMATCH",
        ),
        (lambda fs: [fs[1], fs[0]], "VISION_TIME_INVALID"),
        (lambda fs: [fs[0], fs[0]], "VISION_WINDOW_INVALID"),
        (lambda fs: [replace(fs[0], provenance={})], "VISION_CAMERA_MISMATCH"),
        (lambda fs: [], "VISION_WINDOW_INVALID"),
    ],
)
def test_invalid_windows_never_enqueue(cfg, change, code):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        oid = enroll(store, cfg)
        with pytest.raises(AssistantError) as e:
            VisionService(store, cfg).enqueue(
                change(frames()), [oid], "invalid", "synthetic"
            )
        assert e.value.code == code
        assert store.db.execute("SELECT COUNT(*) FROM memory_jobs").fetchone()[0] == 0


def test_worker_missing_source_is_persisted_fail_without_baseline(cfg):
    cfg = replace(
        cfg,
        vision=replace(
            cfg.vision, upstream_path=str(cfg.assistant.data_dir) + "/missing"
        ),
    )
    with EvidenceStore(cfg.assistant.data_dir) as store:
        oid = enroll(store, cfg)
        job = VisionService(store, cfg).enqueue(frames(), [oid], "missing", "synthetic")
    execute_job(cfg, job["id"])
    with EvidenceStore(cfg.assistant.data_dir) as store:
        job = VisionService(store, cfg).job(job["id"], "synthetic")
        assert job["status"] == "failed"
        assert job["error_code"] == "VISION_SOURCE_MISSING"
        assert job["result"] is None
        assert [s["stage"] for s in job["steps"]] == ["execution_error"]


def test_checkpoint_integrity_and_missing_weights_fail(cfg, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Offline Test",
            "-c",
            "user.email=offline@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "offline fixture",
        ],
        check=True,
        capture_output=True,
    )
    rev = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    weights = tmp_path / "fixture.pt"
    profile = replace(
        cfg.vision,
        upstream_path=str(source),
        upstream_revision=rev,
        checkpoint=str(weights),
    )
    with pytest.raises(AssistantError) as e:
        verify_artifacts(profile)
    assert e.value.code == "VISION_CHECKPOINT_MISSING"
    weights.write_bytes(b"explicitly not a model")
    with pytest.raises(AssistantError) as e:
        verify_artifacts(profile)
    assert e.value.code == "VISION_CHECKPOINT_MISMATCH"


def test_cancellation_beats_late_results_and_worker_restarts_are_isolated(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        oid = enroll(store, cfg)
        svc = VisionService(store, cfg)
        job = svc.enqueue(frames(), [oid], "cancel-late", "synthetic")

    class OfflineCancellationAdapter:
        def __init__(self, profile, emit, check):
            pass

        def run(self, store, payload):
            VisionService(store, cfg).cancel(job["id"], "synthetic")
            return {"fixture": "offline result must never publish"}

    execute_job(cfg, job["id"], adapter_factory=OfflineCancellationAdapter)
    with EvidenceStore(cfg.assistant.data_dir) as store:
        svc = VisionService(store, cfg)
        record = svc.job(job["id"], "synthetic")
        assert record["status"] == "cancelled" and record["result"] is None
        other = svc.enqueue(frames(), [oid], "interrupted", "synthetic")
        svc.jobs.claim(other["id"], "offline-fixture-worker")
        svc.jobs.interrupt()
        assert svc.job(other["id"], "synthetic")["status"] == "running"
        svc.interrupt()
        assert svc.job(other["id"], "synthetic")["status"] == "interrupted"


def test_authenticated_api_snapshot_and_cancel_without_model(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        oid = enroll(store, cfg)
    with TestClient(create_app(cfg)) as client:
        assert client.get("/api/vision").status_code == 401
        client.post("/api/session", json={"token": "offline-test"})
        for _ in range(100):
            state = client.get("/api/state").json()
            if state["camera"]["fresh"]:
                break
            time.sleep(0.02)
        body = {
            "frame_id": state["camera"]["frame_id"],
            "object_ids": [oid],
            "request_key": "api-test",
        }
        response = client.post("/api/vision/jobs", json=body)
        assert response.status_code == 202, response.text
        job = response.json()
        assert job["status"] == "queued" and job["result"] is None
        assert response.headers["cache-control"] == "no-store"
        assert client.post("/api/vision/jobs", json=body).json()["id"] == job["id"]
        cancelled = client.post(f"/api/vision/jobs/{job['id']}/cancel").json()
        assert cancelled["status"] == "cancelled"
        assert client.get("/api/memory").json()["jobs"] == []


def test_missing_reference_foreground_never_becomes_a_center_crop(monkeypatch):
    from teach_and_find.perception.proposals import CandidateProposalGenerator
    from teach_and_find.sim.world3d import build_object_catalog, render_teaching_views

    monkeypatch.setattr(CandidateProposalGenerator, "propose", lambda self, frame: [])
    with pytest.raises(RuntimeError, match="No reference foreground"):
        render_teaching_views(build_object_catalog()["secret_box_1"], angles_deg=(0.0,))


def test_descriptor_readout_is_custom_support_not_identity(cfg):
    from teach_and_find.dinov2_adapter import compare_reference_scores

    refs = [
        {"object_id": "A", "name": "First", "image_shas": ["a1", "a2"]},
        {"object_id": "B", "name": "Second", "image_shas": ["b1"]},
    ]
    result = compare_reference_scores([[0.9, 0.85], [0.6]], refs, "A", cfg.vision)
    assert result["decision"] == "supported_candidate"
    assert result["exact_identity_verified"] is False
    assert result["best_reference_sha"] == "a1"
    assert result["policy_implementation"].startswith("custom_")
    for scores, prompt, reason in [
        ([[0.9, 0.85], [0.6]], "B", "detector_descriptor_disagreement"),
        ([[0.79, 0.7], [0.6]], "A", "insufficient_reference_similarity"),
        ([[0.9, 0.85], [0.89]], "A", "ambiguous_reference_comparison"),
    ]:
        result = compare_reference_scores(scores, refs, prompt, cfg.vision)
        assert result["decision"] == "unresolved" and result["reason"] == reason
    single = compare_reference_scores([[0.9, 0.85]], refs[:1], "A", cfg.vision)
    assert single["margin"] is None and not single["exact_identity_verified"]
    for scores in [[], [[0.9]], [[float("nan"), 0.85], [0.6]]]:
        with pytest.raises(AssistantError) as error:
            compare_reference_scores(scores, refs, "A", cfg.vision)
        assert error.value.code == "DINOV2_OUTPUT_INVALID"


def test_missing_descriptor_fails_before_models_load(cfg, monkeypatch):
    from teach_and_find import yoloe_adapter

    cfg = replace(
        cfg,
        vision=replace(
            cfg.vision, descriptor_source=str(cfg.assistant.data_dir) + "/missing-dino"
        ),
    )
    # This explicit offline artifact-boundary fixture bypasses YOLOE file checks,
    # not inference. Required DINOv2 must stop the job before importing Torch.
    monkeypatch.setattr(
        yoloe_adapter,
        "verify_artifacts",
        lambda profile: {"fixture": "offline_artifact_boundary"},
    )
    with EvidenceStore(cfg.assistant.data_dir) as store:
        oid = enroll(store, cfg)
        job = VisionService(store, cfg).enqueue(
            frames(), [oid], "missing-descriptor", "synthetic"
        )
    execute_job(cfg, job["id"])
    with EvidenceStore(cfg.assistant.data_dir) as store:
        record = VisionService(store, cfg).job(job["id"], "synthetic")
        assert (
            record["status"] == "failed"
            and record["error_code"] == "DINOV2_SOURCE_MISSING"
        )
        assert record["result"] is None
        assert all(step["stage"] != "model_loaded" for step in record["steps"])


def test_legacy_profile_jobs_are_not_silently_upgraded(cfg):
    import json

    with EvidenceStore(cfg.assistant.data_dir) as store:
        oid = enroll(store, cfg)
        svc = VisionService(store, cfg)
        job = svc.enqueue(frames(), [oid], "legacy-profile", "synthetic")
        payload = svc.job(job["id"], "synthetic", internal=True)["payload"]
        payload["profile"].pop("profile_version")
        with store.db:
            store.db.execute(
                "UPDATE memory_jobs SET payload_json=? WHERE id=?",
                (json.dumps(payload), job["id"]),
            )
    execute_job(cfg, job["id"])
    with EvidenceStore(cfg.assistant.data_dir) as store:
        record = VisionService(store, cfg).job(job["id"], "synthetic")
        assert (
            record["status"] == "failed"
            and record["error_code"] == "VISION_PROFILE_UNSUPPORTED"
        )
        assert record["result"] is None
