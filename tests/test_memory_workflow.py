"""Recorded-memory persistence, strict model contracts and API failure handling."""

from dataclasses import replace
import json
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import utc_now
from teach_and_find.memory_service import MemoryService
from teach_and_find.memory_worker import execute_job
from teach_and_find.mind_palace_adapter import (
    ModelTransport,
    object_schema,
    enum,
    array,
)
from teach_and_find.mobile.api import create_app
from teach_and_find.mobile.runtime import OperatorRuntime
from teach_and_find.storage import AssistantError, EvidenceStore
from test_mobile import Device, wait_until


@pytest.fixture
def cfg(tmp_path):
    settings = Settings()
    return replace(
        settings,
        assistant=replace(settings.assistant, data_dir=str(tmp_path)),
        memory=replace(settings.memory, enabled=True),
        mobile=replace(settings.mobile, pairing_token="memory-test", frame_poll_s=0.02),
    )


def frame(number="one"):
    import time

    return CameraFrame(
        np.full((64, 96, 3), 90, np.uint8),
        number,
        utc_now(),
        time.monotonic(),
        0,
        True,
        {"camera_id": "offline-test", "capture_time_basis": "synthetic_render_time"},
    )


def seed(service):
    view = service.register_view("Desk", "Front")
    episode = service.episode("First session", "synthetic")
    job = service.capture(
        frame(), episode["id"], view["id"], "capture-key", "synthetic"
    )
    return view, episode, job


def test_persistent_capture_idempotency_cancellation_and_mode_isolation(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(store, cfg)
        view, episode, job = seed(service)
        assert (
            service.capture(
                frame(), episode["id"], view["id"], "capture-key", "synthetic"
            )["id"]
            == job["id"]
        )
        with pytest.raises(AssistantError, match="different memory input"):
            service.capture(
                frame("different"),
                episode["id"],
                view["id"],
                "capture-key",
                "synthetic",
            )
        with pytest.raises(AssistantError, match="already has a capture"):
            service.capture(
                frame("two"), episode["id"], view["id"], "another-key", "synthetic"
            )
        assert service.claim(job["id"], "test-worker")
        assert service.claim(job["id"], "another-worker") is None
        service.cancel(job["id"], "synthetic")
        with pytest.raises(AssistantError) as exc:
            service.finish(
                service.job(job["id"], "synthetic", internal=True), "succeeded", {}
            )
        assert exc.value.code == "MEMORY_CANCELLED"
        assert (
            store.db.execute("SELECT COUNT(*) FROM memory_descriptions").fetchone()[0]
            == 0
        )
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(store, cfg)
        assert service.job(job["id"], "synthetic")["status"] == "cancelled"
        assert service.overview("physical")["captures"] == []
        with pytest.raises(AssistantError):
            service.job(job["id"], "physical")


class OfflineDescriptionAdapter:
    """Explicit unit fixture, not a runtime provider or capability evaluation."""

    def __init__(self, cfg, step, check):
        self.step, self.check = step, check

    def describe(self, capture, path):
        self.check()
        self.step("describe", {"event": "completed", "test_fixture": True})
        return {
            "description": {
                "objects": ["fixture"],
                "description": "Offline unit fixture",
                "visibility": "clear",
            },
            "provenance": {"test_fixture": True},
        }


def test_question_snapshot_is_immutable_and_restart_does_not_retry(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        view, episode, capture_job = seed(MemoryService(store, cfg))
    execute_job(cfg, capture_job["id"], adapter_factory=OfflineDescriptionAdapter)
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(store, cfg)
        question = service.question(
            "What was recorded?", [episode["id"]], "question-key", "synthetic"
        )
        snapshot = service.job(question["id"], "synthetic", internal=True)["payload"][
            "snapshot"
        ]
        assert len(snapshot) == 1
        second_view = service.register_view("Shelf", "Front")
        second = service.capture(
            frame("two"), episode["id"], second_view["id"], "capture-two", "synthetic"
        )
        assert (
            len(
                service.job(question["id"], "synthetic", internal=True)["payload"][
                    "snapshot"
                ]
            )
            == 1
        )
        service.claim(question["id"], "lost-worker")
        service.interrupt()
        assert service.job(question["id"], "synthetic")["status"] == "interrupted"
        assert service.claim(question["id"], "new-worker") is None
        assert service.job(second["id"], "synthetic")["status"] == "queued"


def test_worker_failure_does_not_create_description(cfg):
    class Broken(OfflineDescriptionAdapter):
        def describe(self, capture, path):
            raise AssistantError("MODEL_CONTRACT_INVALID", "Injected invalid output")

    with EvidenceStore(cfg.assistant.data_dir) as store:
        _, _, job = seed(MemoryService(store, cfg))
    execute_job(cfg, job["id"], adapter_factory=Broken)
    with EvidenceStore(cfg.assistant.data_dir) as store:
        record = MemoryService(store, cfg).job(job["id"], "synthetic")
        assert (
            record["status"] == "failed"
            and record["error_code"] == "MODEL_CONTRACT_INVALID"
        )
        assert (
            store.db.execute("SELECT COUNT(*) FROM memory_descriptions").fetchone()[0]
            == 0
        )


def test_snapshot_budget_is_not_silently_truncated(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(store, cfg)
        _, episode, job = seed(service)
    execute_job(cfg, job["id"], adapter_factory=OfflineDescriptionAdapter)
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(
            store, replace(cfg, memory=replace(cfg.memory, max_snapshot_captures=0))
        )
        with pytest.raises(AssistantError):
            service.question("fixture", [episode["id"]], "key", "synthetic")


@pytest.mark.parametrize(
    "schema,payload",
    [
        (object_schema({"answer": enum(["True", "False"])}), {"answer": "not found"}),
        (
            object_schema({"ready_to_answer": enum(["yes", "no"])}),
            {"ready_to_answer": "not yes"},
        ),
        (
            object_schema({"place_number": array({"type": "integer", "enum": [1]})}),
            {"place_number": []},
        ),
        (
            object_schema({"citations": array(enum(["allowed"]))}),
            {"citations": ["unknown"]},
        ),
    ],
)
def test_invalid_contract_cannot_reach_upstream_conversion(cfg, schema, payload):
    response = SimpleNamespace(
        model=cfg.memory.model,
        id="offline-response",
        usage=None,
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(refusal=None, content=json.dumps(payload)),
            )
        ],
    )
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return response

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    transport = ModelTransport(cfg, lambda *_: None, lambda: None, client=client)
    transport.prepare("verify", schema)
    with pytest.raises(AssistantError) as exc:
        transport.call([])
    assert exc.value.code == "MODEL_CONTRACT_INVALID"
    assert len(requests) == 1
    assert transport.last is None


def test_api_capture_freezes_frame_and_stale_retry_is_idempotent(cfg):
    device = Device()
    runtime = OperatorRuntime(cfg, device)
    with TestClient(create_app(cfg, runtime=runtime)) as client:
        assert client.get("/api/memory").status_code == 401
        headers = {"origin": "http://testserver"}
        client.post("/api/session", json={"token": "memory-test"}, headers=headers)
        wait_until(lambda: runtime.latest is not None)
        view = client.post(
            "/api/memory/views",
            json={"region_name": "Desk", "viewpoint_name": "Front"},
            headers=headers,
        ).json()
        episode = client.post(
            "/api/memory/episodes", json={"name": "Session"}, headers=headers
        ).json()
        body = {
            "frame_id": runtime.latest.frame_id,
            "view_id": view["id"],
            "episode_id": episode["id"],
            "request_key": "request-one",
        }
        response = client.post("/api/memory/captures", json=body, headers=headers)
        assert response.status_code == 202, response.text
        job = response.json()
        runtime.frames.clear()
        repeated = client.post("/api/memory/captures", json=body, headers=headers)
        assert repeated.status_code == 202 and repeated.json()["id"] == job["id"]
        assert (
            client.post(f"/api/memory/jobs/{job['id']}/cancel", headers=headers).json()[
                "status"
            ]
            == "cancelled"
        )
        assert (
            client.post(
                "/api/memory/captures",
                json={**body, "request_key": "stale"},
                headers=headers,
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/memory/questions",
                json={
                    "question": "fixture",
                    "episode_ids": [episode["id"]],
                    "request_key": "q",
                },
                headers=headers,
            ).status_code
            == 422
        )
        assert client.get("/api/memory").headers["cache-control"] == "no-store"


def test_cancellation_during_inference_rejects_late_description(cfg):
    class Cancelling(OfflineDescriptionAdapter):
        def describe(self, capture, path):
            with EvidenceStore(cfg.assistant.data_dir) as other:
                row = other.db.execute(
                    "SELECT id FROM memory_jobs WHERE status='running'"
                ).fetchone()
                MemoryService(other, cfg).cancel(row[0], "synthetic")
            return super().describe(capture, path)

    with EvidenceStore(cfg.assistant.data_dir) as store:
        _, _, job = seed(MemoryService(store, cfg))
    execute_job(cfg, job["id"], adapter_factory=Cancelling)
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(store, cfg)
        assert service.job(job["id"], "synthetic")["status"] == "cancelled"
        assert (
            store.db.execute("SELECT COUNT(*) FROM memory_descriptions").fetchone()[0]
            == 0
        )


def test_model_profile_and_budgets_are_frozen_at_submission(cfg):
    profiles = []

    class Recording(OfflineDescriptionAdapter):
        def __init__(self, settings, step, check):
            profiles.append(settings.memory)
            super().__init__(settings, step, check)

    with EvidenceStore(cfg.assistant.data_dir) as store:
        _, _, job = seed(MemoryService(store, cfg))
    changed = replace(
        cfg, memory=replace(cfg.memory, model="changed-after-submission", max_calls=1)
    )
    execute_job(changed, job["id"], adapter_factory=Recording)
    assert profiles == [cfg.memory]


def test_real_adapter_rejects_missing_source_and_tampered_image(cfg, tmp_path):
    from teach_and_find.mind_palace_adapter import load_upstream, MindPalaceAdapter

    with pytest.raises(AssistantError) as exc:
        load_upstream(
            replace(
                cfg, memory=replace(cfg.memory, upstream_path=str(tmp_path / "missing"))
            )
        )
    assert exc.value.code == "UPSTREAM_UNAVAILABLE"
    path = tmp_path / "evidence.png"
    path.write_bytes(b"corrupted")
    with pytest.raises(AssistantError) as exc:
        MindPalaceAdapter.image({"image_sha": "incorrect"}, path)
    assert exc.value.code == "EVIDENCE_INTEGRITY"


def test_question_does_not_omit_a_failed_or_pending_view(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        _, episode, job = seed(MemoryService(store, cfg))
    execute_job(cfg, job["id"], adapter_factory=OfflineDescriptionAdapter)
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(store, cfg)
        view = service.register_view("Shelf", "Front")
        pending = service.capture(
            frame("second"), episode["id"], view["id"], "pending", "synthetic"
        )
        service.cancel(pending["id"], "synthetic")
        with pytest.raises(AssistantError) as exc:
            service.question(
                "Compare these regions", [episode["id"]], "question", "synthetic"
            )
        assert exc.value.code == "MEMORY_DESCRIPTION_REQUIRED"


@pytest.mark.parametrize(
    "model,finish,code",
    [
        ("different-model", "stop", "MODEL_MISMATCH"),
        ("gpt-6-luna", "length", "MODEL_INCOMPLETE"),
    ],
)
def test_wrong_model_and_incomplete_output_cannot_become_answers(
    cfg, model, finish, code
):
    response = SimpleNamespace(
        model=model,
        id="offline",
        usage=None,
        choices=[
            SimpleNamespace(
                finish_reason=finish,
                message=SimpleNamespace(refusal=None, content='{"answer":"True"}'),
            )
        ],
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    )
    transport = ModelTransport(cfg, lambda *_: None, lambda: None, client=client)
    transport.prepare("verify", object_schema({"answer": enum(["True", "False"])}))
    with pytest.raises(AssistantError) as exc:
        transport.call([])
    assert exc.value.code == code
    assert transport.last is None


def test_missing_image_cannot_be_replaced_by_another_capture(tmp_path):
    from teach_and_find.mind_palace_adapter import MindPalaceAdapter

    with pytest.raises(AssistantError) as exc:
        MindPalaceAdapter.image({"image_sha": "unavailable"}, tmp_path / "missing.png")
    assert exc.value.code == "MEMORY_IMAGE_MISSING"


def test_capture_worker_uses_exact_id_beyond_history_window(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(store, cfg)
        episode = service.episode("Many viewpoints", "synthetic")
        for i in range(cfg.memory.max_snapshot_captures + 2):
            view = service.register_view("Desk", f"View {i}")
            job = service.capture(
                frame(str(i)), episode["id"], view["id"], f"capture-{i}", "synthetic"
            )
        limited = MemoryService(
            store, replace(cfg, memory=replace(cfg.memory, history_limit=1))
        )
        assert limited.overview("synthetic")["captures"][0]["frame_id"] == str(i)
    execute_job(cfg, job["id"], adapter_factory=OfflineDescriptionAdapter)
    with EvidenceStore(cfg.assistant.data_dir) as store:
        service = MemoryService(store, cfg)
        assert service.job(job["id"], "synthetic")["status"] == "succeeded"
        described = store.db.execute(
            "SELECT capture_id FROM memory_descriptions"
        ).fetchall()
        assert [r[0] for r in described] == [
            service.job(job["id"], "synthetic", internal=True)["payload"]["capture_id"]
        ]


def test_worker_total_budget_cannot_be_bypassed_by_queued_profile(cfg, tmp_path):
    from teach_and_find.memory_budget import reserve_call

    # The app queued this job before a worker-wide cap was configured.
    with EvidenceStore(cfg.assistant.data_dir) as store:
        _, _, job = seed(MemoryService(store, cfg))
    worker = replace(
        cfg,
        memory=replace(
            cfg.memory,
            global_call_budget_file=str(tmp_path / "worker-budget.json"),
            global_call_budget=1,
        ),
    )

    class BudgetFixture(OfflineDescriptionAdapter):
        def __init__(self, settings, step, check):
            self.settings = settings
            super().__init__(settings, step, check)

        def describe(self, capture, path):
            reserve_call(self.settings.memory)
            reserve_call(self.settings.memory)
            raise AssertionError("The second reservation must fail closed.")

    execute_job(worker, job["id"], adapter_factory=BudgetFixture)
    with EvidenceStore(cfg.assistant.data_dir) as store:
        result = MemoryService(store, cfg).job(job["id"], "synthetic")
        assert result["status"] == "failed"
        assert result["error_code"] == "MODEL_GLOBAL_BUDGET_EXHAUSTED"
        assert (
            store.db.execute("SELECT COUNT(*) FROM memory_descriptions").fetchone()[0]
            == 0
        )
    assert json.loads((tmp_path / "worker-budget.json").read_text())["attempts"] == 1
