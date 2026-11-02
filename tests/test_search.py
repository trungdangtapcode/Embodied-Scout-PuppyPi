"""Offline search lifecycle, evidence and ambiguity regressions; no model downloads."""

from dataclasses import replace
import copy

import numpy as np
import pytest

from teach_and_find.config import Settings
from teach_and_find.errors import AssistantError
from teach_and_find.library import build_library
from teach_and_find.search_service import SearchService
from teach_and_find.search_verification import assess_views
from teach_and_find.sim.search_device import fixture_calibration
from teach_and_find.storage import EvidenceStore


@pytest.fixture
def search(tmp_path):
    cfg = Settings()
    cfg = replace(
        cfg,
        search=replace(cfg.search, enabled=True),
        vision=replace(cfg.vision, enabled=True),
    )
    with EvidenceStore(tmp_path) as store:
        lib = build_library(store, cfg)
        image = np.random.default_rng(1).integers(0, 255, (64, 64, 3), np.uint8)
        target = lib.teach("target", [image, image[:, ::-1].copy()])
        yield SearchService(store, cfg), target, cfg


def test_missing_worker_is_failure_and_references_are_immutable(search):
    service, target, cfg = search
    with pytest.raises(AssistantError, match="separate search worker"):
        service.create(
            target["id"], "owner", "request", fixture_calibration(), "synthetic"
        )
    service.seen()
    run = service.create(
        target["id"], "owner", "request", fixture_calibration(), "synthetic"
    )
    assert run["status"] == "queued"
    assert (
        service.create(
            target["id"], "owner", "request", fixture_calibration(), "synthetic"
        )["id"]
        == run["id"]
    )
    old = run["payload"]["references"][0]["image_shas"]
    build_library(service.store, cfg).teach(
        "target", [np.full((32, 32, 3), 255, np.uint8)], object_id=target["id"]
    )
    assert service.get(run["id"])["payload"]["references"][0]["image_shas"] == old
    with pytest.raises(AssistantError, match="one station search"):
        service.create(
            target["id"], "owner", "other-key", fixture_calibration(), "synthetic"
        )


def test_cancel_and_restart_cannot_publish_late_sightings(search):
    service, target, _ = search
    service.seen()
    queued = service.create(
        target["id"], "owner", "request", fixture_calibration(), "synthetic"
    )
    run = service.claim()
    assert run["id"] == queued["id"]
    service.cancel_all()
    with pytest.raises(AssistantError):
        service.finish(run["id"], {"verdict": "confirmed"}, {"object_id": target["id"]})
    assert service.overview()["sightings"] == []
    assert service.get(run["id"])["status"] == "cancelled"
    second = service.create(
        target["id"], "owner", "second", fixture_calibration(), "synthetic"
    )
    service.interrupt()
    assert service.claim() is None
    assert service.get(second["id"])["status"] == "interrupted"


def view(x, refs, location=(-0.3, 2.0)):
    return {
        "pose": {"x": x, "y": 1.2, "yaw": 1.57},
        "candidates": [
            {
                "object_id": "target",
                "detection_index": 0,
                "descriptor_supported": True,
                "floor_xy": list(location),
                "matches": [{"reference_index": i, "supported": True} for i in refs],
            }
        ],
    }


def test_multiview_requires_baseline_all_references_and_same_spatial_instance():
    cfg = Settings().search
    calibration = fixture_calibration()

    def assess(views):
        return assess_views(views, "target", 2, calibration, cfg)

    assert assess([view(-0.3, [0]), view(0.3, [1])])["verdict"] == "confirmed"
    for views in [
        [view(-0.3, [0, 1])],
        [view(-0.3, [0]), view(-0.29, [1])],
        [view(-0.3, [0]), view(0.3, [0])],
        [view(-0.3, [0]), view(0.3, [1], (0.3, 2.0))],
        [view(-0.3, [0], (0.0, 2.0)), view(0.3, [1], (0.0, 2.0))],
    ]:
        assert assess(views)["verdict"] == "inconclusive"
    ambiguous = [
        view(-0.3, [0]),
        view(0.3, [1]),
        view(-0.3, [0], (0.3, 2.0)),
        view(0.3, [1], (0.3, 2.0)),
    ]
    assert assess(ambiguous)["reason"] == "multiple_supported_instances"
    rejected = [view(-0.3, [0]), view(0.3, [1])]
    rejected = copy.deepcopy(rejected)
    rejected[0]["candidates"][0]["descriptor_supported"] = False
    assert assess(rejected)["verdict"] == "inconclusive"


def test_control_uses_latest_status_and_expires_intent_during_slow_capture(monkeypatch):
    """A camera request must not queue challenges or perpetuate a stalled motion."""
    import cv2
    from datetime import datetime, timezone
    import json
    import queue
    import sys
    import threading
    import time
    from types import SimpleNamespace
    from teach_and_find.search_transport import SearchConnection

    messages = queue.Queue()
    ended = threading.Event()
    commands = []
    owned = threading.Event()
    png = cv2.imencode(".jpg", np.full((32, 32, 3), 120, np.uint8))[1].tobytes()
    stamps = {}

    class Response:
        content = png

        def raise_for_status(self):
            return None

    class HTTP:
        cookies = {"puppypi_session": "disposable-test"}

        def post(self, *args, **kwargs):
            return Response()

        def get(self, *args, params, **kwargs):
            # Greater than a status period, less than the capture freshness limit.
            time.sleep(0.22)
            response = Response()
            response.headers = {
                "X-Frame-Id": params["id"],
                "X-Captured-At": stamps[params["id"]],
            }
            return response

        def close(self):
            pass

    class Socket:
        def recv(self):
            return messages.get(timeout=2)

        def send(self, payload):
            message = json.loads(payload)
            if message["type"] == "arm":
                owned.set()
                messages.put(json.dumps({"type": "armed", "epoch": "test-epoch"}))
            elif message["type"] == "drive":
                assert time.monotonic() - float(message["challenge"]) < 0.3
                commands.append((time.monotonic(), message))
            elif message["type"] == "search_disarm":
                owned.clear()
                messages.put(
                    json.dumps(
                        {
                            "type": "search_disarmed",
                            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                )

        def close(self):
            ended.set()
            messages.put("{}")

    def producer():
        index = 0
        while not ended.wait(0.025):
            index += 1
            identifier = str(index)
            stamps[identifier] = datetime.now(timezone.utc).isoformat()
            messages.put(
                json.dumps(
                    {
                        "type": "status",
                        "connected": True,
                        "camera": {
                            "fresh": True,
                            "frame_id": identifier,
                            "provenance": {
                                "camera_id": "test",
                                "session_id": "one",
                                "calibration_id": "test-calibration",
                            },
                        },
                        "control": {
                            "owned": owned.is_set(),
                            "challenge": str(time.monotonic()),
                        },
                    }
                )
            )

    monkeypatch.setenv("PUPPYPI_OPERATOR_TOKEN", "test")
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(Session=HTTP))
    monkeypatch.setitem(
        sys.modules,
        "websocket",
        SimpleNamespace(create_connection=lambda *a, **k: Socket()),
    )
    thread = threading.Thread(target=producer, daemon=True)
    thread.start()
    connection = None
    try:
        connection = SearchConnection(
            Settings().search, "test-search", "test-calibration"
        )
        connection.drive(1.0, 0.0)
        started = time.monotonic()
        time.sleep(0.65)
        connection.check()
        assert any(command["forward"] == 1 for _, command in commands)
        late = [command for at, command in commands if at > started + 0.4]
        assert late and all(command["forward"] == 0 for command in late)
        assert messages.qsize() < 3
        connection.disarm()
        sent = len(commands)
        time.sleep(0.55)
        connection.check()
        assert not owned.is_set()
        assert len(commands) == sent
        capture = connection.stationary_capture()
        assert datetime.fromisoformat(capture["captured_at"]) > connection.disarmed_at
    finally:
        if connection:
            connection.close()
        ended.set()
        thread.join(2)


def test_no_cookie_disclosure_or_unlinked_success_publication(search):
    service, target, _ = search
    service.seen()
    run = service.create(
        target["id"],
        "session-cookie-secret",
        "request",
        fixture_calibration(),
        "synthetic",
    )
    assert "session-cookie-secret" not in str(run)
    assert "owner" not in run
    service.claim()
    with pytest.raises(AssistantError, match="stored capture"):
        service.finish(
            run["id"],
            {"verdict": "confirmed"},
            {
                "object_id": target["id"],
                "mode": "synthetic",
                "search_id": run["id"],
                "station": "Station_A",
                "evidence_views": [
                    {"ordinal": 0, "frame": {}},
                    {"ordinal": 1, "frame": {}},
                ],
            },
        )
    assert service.overview()["sightings"] == []


def test_unqualified_policy_cannot_write_automatic_memory(search):
    service, target, _ = search
    service.seen()
    run = service.create(
        target["id"], "owner", "request", fixture_calibration(), "synthetic"
    )
    service.claim()
    shas = run["payload"]["references"][0]["image_shas"]
    evidence = []
    for index, sha in enumerate(shas):
        frame = {
            "image_sha": sha,
            "frame_id": str(index),
            "captured_at": run["created_at"],
        }
        service.view(run["id"], {"frame": frame})
        evidence.append({"ordinal": index, "frame": frame})
    sighting = {
        "object_id": target["id"],
        "mode": "synthetic",
        "search_id": run["id"],
        "station": "Station_A",
        "evidence_views": evidence,
    }
    with pytest.raises(AssistantError, match="has not passed"):
        service.finish(run["id"], {"verdict": "confirmed"}, sighting)
    assert service.overview()["sightings"] == []
    assert service.get(run["id"])["status"] == "running"


def test_cancelling_an_old_run_cannot_cancel_the_next_run(search):
    service, target, _ = search
    service.seen()
    old = service.create(
        target["id"], "owner", "old", fixture_calibration(), "synthetic"
    )
    service.cancel_one(old["id"])
    new = service.create(
        target["id"], "owner", "new", fixture_calibration(), "synthetic"
    )
    assert service.cancel_one(old["id"])["status"] == "cancelled"
    assert service.get(new["id"])["status"] == "queued"


def test_polling_summaries_do_not_transfer_archived_pose_or_match_arrays(search):
    import json

    service, target, _ = search
    service.seen()
    run = service.create(
        target["id"], "owner", "request", fixture_calibration(), "synthetic"
    )
    service.claim()
    for index in range(20):
        service.event(
            run["id"],
            "pose_observed",
            {"sequence": index, "diagnostic_pixels": list(range(500))},
        )
    overview = service.overview()
    assert len(json.dumps(overview)) < 10000
    assert "events" not in overview["runs"][0] and "payload" not in overview["runs"][0]
    assert "events" not in service.detail(run["id"])
    assert len(service.detail(run["id"], export=True)["events"]) == 20
