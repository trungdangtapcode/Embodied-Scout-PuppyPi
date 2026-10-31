"""Local browser API, evidence, ownership and stop regression tests; no robot."""

from dataclasses import replace
import io
import json
import sqlite3
import threading
import time
import zipfile

import cv2
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import numpy as np
import pytest

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import utc_now
from teach_and_find.mobile.api import create_app
from teach_and_find.mobile.runtime import OperatorRuntime
from teach_and_find.storage import EvidenceStore, MIGRATIONS


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Condition did not become true.")


class Device:
    mode = "synthetic"

    def __init__(self):
        self.commands = []
        self.closed = False
        self.fresh = True
        self.started = threading.Event()
        self.release = threading.Event()
        self.block_motion = False
        self.sequence = 0

    def read_frame(self):
        self.sequence += 1
        return CameraFrame(
            np.full((96, 128, 3), 120, np.uint8),
            str(self.sequence),
            utc_now(),
            time.monotonic(),
            0 if self.fresh else 10,
            self.fresh,
            {"camera_id": "test", "sequence": self.sequence},
        )

    def send_command(self, command):
        if self.block_motion and command.vx_cm_s:
            self.started.set()
            assert self.release.wait(2)
        self.commands.append(command)

    def close(self):
        self.closed = True


@pytest.fixture
def configured(tmp_path):
    cfg = Settings()
    return replace(
        cfg,
        assistant=replace(cfg.assistant, data_dir=str(tmp_path)),
        mobile=replace(cfg.mobile, pairing_token="local-test-code", frame_poll_s=0.02),
    )


@pytest.fixture
def client(configured):
    device = Device()
    runtime = OperatorRuntime(configured, device)
    app = create_app(configured, runtime=runtime)
    with TestClient(app) as client:
        wait_until(lambda: runtime.connected)
        yield client, runtime, device
    assert device.closed
    assert all(not thread.is_alive() for thread in runtime.threads)


def pair(client):
    assert (
        client.post("/api/session", json={"token": "local-test-code"}).status_code
        == 200
    )


def next_message(ws, kind, predicate=lambda message: True):
    for _ in range(100):
        result = ws.receive_json()
        if result["type"] == kind and predicate(result):
            return result
    raise AssertionError(f"Missing {kind}")


def test_pairing_origin_and_evidence_lifecycle(client):
    c, runtime, _ = client
    assert c.get("/api/objects").status_code == 401
    assert c.post("/api/session", json={"token": "wrong"}).status_code == 401
    pair(c)
    assert (
        c.post("/api/stop", headers={"Origin": "https://elsewhere.example"}).status_code
        == 403
    )
    assert c.get("/api/state").headers["cache-control"] == "no-store"
    image = np.full((80, 80, 3), 210, np.uint8)
    image[20:60, 20:60] = [40, 100, 190]
    _, png = cv2.imencode(".png", image)
    result = c.post(
        "/api/objects",
        data={"name": "Tool case"},
        files={"files": ("crop.png", png.tobytes(), "image/png")},
    )
    assert result.status_code == 200, result.text
    obj = result.json()
    assert (
        c.post(
            "/api/objects",
            data={"name": "bad"},
            files={"files": ("bad.png", b"bad", "image/png")},
        ).status_code
        == 422
    )
    assert (
        c.get("/api/evidence/" + obj["references"][0]["image_sha"]).headers[
            "content-type"
        ]
        == "image/png"
    )
    frame = runtime.latest.frame_id
    result = c.post(
        "/api/observations",
        json={
            "object_id": obj["id"],
            "frame_id": frame,
            "station": "Station_A",
            "assertion": "present",
            "visibility": 1,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["provenance"]["camera_id"] == "test"
    assert (
        c.get(f"/api/objects/{obj['id']}/history").json()["observations"][0]["id"]
        == result.json()["id"]
    )
    checklist = c.post(
        "/api/checklists",
        json={
            "name": "Readiness",
            "items": [{"object_id": obj["id"], "station": "Station_A"}],
        },
    ).json()
    report = c.post(f"/api/checklists/{checklist['id']}/inspect").json()
    assert report["summary"] == {"pass": 1, "fail": 0, "unknown": 0}
    archive = c.get(f"/api/reports/{report['id']}/download")
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        assert any(name.endswith(".html") for name in bundle.namelist())
        assert any(name.endswith(".png") for name in bundle.namelist())
    assert (
        c.patch(f"/api/objects/{obj['id']}", json={"name": "Renamed"}).json()["name"]
        == "Renamed"
    )
    assert c.delete(f"/api/objects/{obj['id']}").status_code == 200
    assert c.get("/api/objects").json() == []
    assert c.get(f"/api/objects/{obj['id']}/history").status_code == 200


def test_socket_ownership_disconnect_stale_frame_and_replay(client):
    c, runtime, device = client
    pair(c)
    with c.websocket_connect("/api/live") as ws:
        status = next_message(ws, "status")
        ws.send_json(
            {
                "type": "arm",
                "challenge": status["control"]["challenge"],
                "frame_id": status["camera"]["frame_id"],
            }
        )
        armed = next_message(ws, "armed")
        with c.websocket_connect("/api/live") as observer:
            other = next_message(observer, "status")
            observer.send_json(
                {
                    "type": "arm",
                    "challenge": other["control"]["challenge"],
                    "frame_id": other["camera"]["frame_id"],
                }
            )
            assert next_message(observer, "error")["code"] == "CONTROL_BUSY"
        assert runtime.gate.owner is not None
        status = next_message(ws, "status", lambda s: s["control"]["owned"])
        payload = {
            "type": "drive",
            "challenge": status["control"]["challenge"],
            "frame_id": status["camera"]["frame_id"],
            "epoch": armed["epoch"],
            "sequence": 1,
            "forward": 0.5,
            "turn": 0,
        }
        ws.send_json(payload)
        wait_until(lambda: any(cmd.vx_cm_s == 3 for cmd in device.commands))
        ws.send_json(payload)
        assert next_message(ws, "error")["code"] == "STALE_CONTROL"
        wait_until(lambda: device.commands[-1].vx_cm_s == 0)
        status = next_message(ws, "status", lambda s: not s["control"]["armed"])
        ws.send_json(
            {
                "type": "arm",
                "challenge": status["control"]["challenge"],
                "frame_id": status["camera"]["frame_id"],
            }
        )
        next_message(ws, "armed")
    wait_until(lambda: runtime.gate.owner is None)
    device.fresh = False
    wait_until(lambda: not runtime.status()["control"]["ready"])
    assert (
        c.post(
            "/api/observations",
            json={
                "object_id": "not-needed",
                "station": "A",
                "assertion": "present",
                "frame_id": runtime.latest.frame_id,
            },
        ).status_code
        == 409
    )


def test_stop_during_inflight_motion_still_sends_zero(configured):
    device = Device()
    device.block_motion = True
    runtime = OperatorRuntime(configured, device)
    runtime.start()
    try:
        wait_until(lambda: runtime.connected)
        status = runtime.status()
        armed = runtime.arm(
            "alice", status["control"]["challenge"], status["camera"]["frame_id"]
        )
        runtime.drive(
            "alice",
            {
                "epoch": armed["epoch"],
                "sequence": 1,
                "challenge": status["control"]["challenge"],
                "frame_id": status["camera"]["frame_id"],
                "forward": 1,
                "turn": 0,
            },
        )
        assert device.started.wait(1)
        runtime.stop()
        device.release.set()
        wait_until(
            lambda: len(device.commands) >= 2 and device.commands[-1].vx_cm_s == 0
        )
    finally:
        device.release.set()
        runtime.close()


def test_monitor_only_never_opens_command_path(configured):
    device = Device()
    device.mode = "physical"
    runtime = OperatorRuntime(configured, device)
    runtime.start()
    try:
        wait_until(lambda: runtime.connected)
        assert not runtime.status()["control"]["enabled"]
        runtime.stop()
    finally:
        runtime.close()
    assert device.commands == []


def test_schema_v2_migration_preserves_old_evidence(tmp_path):
    db = sqlite3.connect(tmp_path / "assistant.sqlite3")
    for migration in MIGRATIONS[:2]:
        for statement in migration:
            db.execute(statement)
    db.execute(
        "INSERT INTO objects VALUES ('obj','box','box','baseline',1,'now','now',NULL)"
    )
    db.execute(
        "INSERT INTO observations VALUES ('obs','obj','A','present','then','now','sha',1,1,'operator','physical')"
    )
    db.execute("PRAGMA user_version=2")
    db.commit()
    db.close()
    with EvidenceStore(tmp_path) as store:
        row = dict(store.db.execute("SELECT * FROM observations").fetchone())
        assert row["image_sha"] == "sha" and row["captured_at"] == "then"
        assert json.loads(row["provenance_json"]) == {}
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 3


def test_synthetic_seed_is_explicit_and_not_repeatable(client):
    c, _, _ = client
    pair(c)
    assert c.get("/api/objects").json() == []
    result = c.post("/api/demo")
    assert result.status_code == 200, result.text
    assert result.json()["report"]["summary"] == {"pass": 1, "fail": 1, "unknown": 1}
    assert c.post("/api/demo").status_code == 409


def test_expired_session_revokes_armed_socket(client):
    c, runtime, _ = client
    pair(c)
    with c.websocket_connect("/api/live") as ws:
        status = next_message(ws, "status")
        ws.send_json(
            {
                "type": "arm",
                "challenge": status["control"]["challenge"],
                "frame_id": status["camera"]["frame_id"],
            }
        )
        next_message(ws, "armed")
        with c.app.state.sessions.lock:
            c.app.state.sessions.sessions.clear()
        with pytest.raises(WebSocketDisconnect):
            for _ in range(10):
                ws.receive_json()
    wait_until(lambda: runtime.gate.owner is None)
    assert c.get("/api/objects").status_code == 401


def test_invalid_socket_contract_disarms_owner(client):
    c, runtime, _ = client
    pair(c)
    with c.websocket_connect("/api/live") as ws:
        status = next_message(ws, "status")
        ws.send_json(
            {
                "type": "arm",
                "challenge": status["control"]["challenge"],
                "frame_id": status["camera"]["frame_id"],
            }
        )
        next_message(ws, "armed")
        ws.send_json({"type": "drive", "arbitrary_code": "never executed"})
        assert next_message(ws, "error")["code"] == "INVALID_MESSAGE"
        assert runtime.gate.owner is None
