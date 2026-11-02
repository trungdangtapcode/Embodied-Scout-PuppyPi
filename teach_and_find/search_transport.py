"""Latest-only camera/status transport with independent expiring control intents.

Receiver drains WebSocket status continuously into one slot. Camera HTTP never
blocks the control sender. Model/producer stalls expire movement to zero; a lost
lease is terminal and never automatically rearmed.
"""

import json
from datetime import datetime, timezone
import os
import threading
import time
from urllib.parse import urlparse

import cv2
import numpy as np

from teach_and_find.errors import AssistantError


def sample_age(sample):
    captured = datetime.fromisoformat(sample["captured_at"])
    if captured.tzinfo is None:
        raise AssistantError(
            "SEARCH_CAPTURE_CLOCK_INVALID",
            "Capture time needs a verified host timezone.",
        )
    age = (datetime.now(timezone.utc) - captured).total_seconds()
    if age < -0.05:
        raise AssistantError(
            "SEARCH_CAPTURE_CLOCK_INVALID", "Capture time is in the future."
        )
    return max(age, time.monotonic() - sample["received_at"])


class SearchConnection:
    def __init__(self, cfg, search_id, calibration_id, camera_identity=None):
        import requests
        import websocket

        self.cfg = cfg
        self.calibration_id = calibration_id
        self.http = requests.Session()
        token = os.environ.get("PUPPYPI_OPERATOR_TOKEN")
        if not token:
            raise AssistantError(
                "SEARCH_PAIRING_REQUIRED",
                "Set the host pairing token in the worker environment.",
            )
        self.base = cfg.host_url.rstrip("/")
        parsed = urlparse(self.base)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise AssistantError(
                "SEARCH_HOST_UNSUPPORTED",
                "This simulator profile requires a loopback host.",
            )
        response = self.http.post(
            self.base + "/api/session", json={"token": token}, timeout=3
        )
        response.raise_for_status()
        self.socket = websocket.create_connection(
            self.base.replace("http://", "ws://").replace("https://", "wss://")
            + "/api/live?search_id="
            + search_id,
            cookie="; ".join(f"{k}={v}" for k, v in self.http.cookies.items()),
            origin=self.base,
            timeout=3,
        )
        self.lock, self.closed, self.started = (
            threading.Lock(),
            threading.Event(),
            threading.Event(),
        )
        self.error = None
        self.camera_identity = camera_identity
        self.disarming = threading.Event()
        self.disarmed = threading.Event()
        self.disarmed_at = None
        self.send_lock = threading.Lock()
        self.intent, self.intent_until = (0.0, 0.0), 0.0
        self.sample, self.status, self.epoch = None, None, None
        self.armed_at = 0.0
        self.threads = [
            threading.Thread(target=lambda task=task: self._guard(task), daemon=True)
            for task in (self._receive, self._capture, self._send)
        ]
        for thread in self.threads:
            thread.start()
        if not self.started.wait(5) or self.error:
            self.close()
            raise AssistantError(
                "SEARCH_CONTROL_UNAVAILABLE",
                str(self.error or "Arm handshake timed out."),
            )

    def _guard(self, task):
        try:
            task()
        except Exception as error:
            if not self.closed.is_set():
                self.error = error
                self.started.set()
                self.closed.set()
                self.socket.close()  # Host disconnect independently zeros movement.

    def _receive(self):
        while not self.closed.is_set():
            message = json.loads(self.socket.recv())
            if message["type"] == "error":
                raise AssistantError(
                    message["code"], message.get("message", "Control failed.")
                )
            with self.lock:
                if message["type"] == "armed":
                    self.epoch, self.armed_at = message["epoch"], time.monotonic()
                    self.started.set()
                elif message["type"] == "status":
                    self.status = (message, time.monotonic())
                elif message["type"] == "search_disarmed":
                    self.disarmed_at = datetime.fromisoformat(
                        message["acknowledged_at"]
                    )
                    self.disarmed.set()

    def _capture(self):
        previous, identity = None, self.camera_identity
        while not self.closed.wait(0.04):
            with self.lock:
                status = self.status
            if status is None:
                continue
            message = status[0]
            camera = message["camera"]
            if not camera["fresh"] or not message["connected"]:
                raise AssistantError("SEARCH_CAMERA_STALE", "Fresh camera unavailable.")
            if camera["provenance"].get("calibration_id") != self.calibration_id:
                raise AssistantError(
                    "SEARCH_CALIBRATION_MISMATCH",
                    "Capture calibration differs from the registered search map.",
                )
            current_identity = (
                camera["provenance"].get("camera_id"),
                camera["provenance"].get("session_id"),
            )
            if not all(current_identity) or (
                identity is not None and identity != current_identity
            ):
                raise AssistantError(
                    "SEARCH_CAMERA_SESSION_CHANGED",
                    "Camera/session changed; start a new search.",
                )
            identity = current_identity
            self.camera_identity = identity
            if previous == camera["frame_id"]:
                continue
            response = self.http.get(
                self.base + "/api/frame.jpg",
                params={"id": camera["frame_id"]},
                timeout=0.8,
            )
            response.raise_for_status()
            image = cv2.imdecode(
                np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR
            )
            if (
                image is None
                or response.headers.get("X-Frame-Id") != camera["frame_id"]
            ):
                raise AssistantError(
                    "SEARCH_CAMERA_INVALID", "Frame ID or pixels invalid."
                )
            with self.lock:
                self.sample = {
                    "image": image,
                    "frame_id": camera["frame_id"],
                    "captured_at": response.headers["X-Captured-At"],
                    "provenance": camera["provenance"],
                    "received_at": time.monotonic(),
                }
            previous = camera["frame_id"]

    def _send(self):
        # Serialize phase transition with sends: never emit drive after disarm.
        def send(payload):
            with self.send_lock:
                if not self.disarming.is_set():
                    self.socket.send(json.dumps(payload))

        requested, sequence = False, 0
        while not self.closed.wait(0.08):
            if self.disarming.is_set():
                continue
            now = time.monotonic()
            with self.lock:
                status, sample, epoch, armed_at = (
                    self.status,
                    self.sample,
                    self.epoch,
                    self.armed_at,
                )
                forward, turn = self.intent if now <= self.intent_until else (0.0, 0.0)
            if status is None or sample is None:
                continue
            message, received = status
            if now - received > 0.3 or sample_age(sample) > self.cfg.pose_max_age_s:
                raise AssistantError(
                    "SEARCH_CAMERA_OR_STATUS_STALE",
                    "Camera/status transport expired; no motion renewal.",
                )
            control = message["control"]
            if epoch is None:
                if not requested:
                    send(
                        {
                            "type": "arm",
                            "challenge": control["challenge"],
                            "frame_id": sample["frame_id"],
                        }
                    )
                    requested = True
                continue
            if received <= armed_at:
                continue
            if not control["owned"]:
                raise AssistantError(
                    "SEARCH_CONTROL_LOST",
                    "Stop, expiry or takeover revoked motion; no automatic rearm.",
                )
            sequence += 1
            send(
                {
                    "type": "drive",
                    "epoch": epoch,
                    "sequence": sequence,
                    "challenge": control["challenge"],
                    "frame_id": sample["frame_id"],
                    "forward": forward,
                    "turn": turn,
                }
            )

    def check(self):
        if self.error or self.closed.is_set():
            raise AssistantError(
                "SEARCH_CONTROL_LOST", str(self.error or "Transport stopped.")
            )

    def latest(self):
        self.check()
        with self.lock:
            if self.sample is None or sample_age(self.sample) > self.cfg.pose_max_age_s:
                raise AssistantError(
                    "SEARCH_CAMERA_STALE", "Latest image expired; motion stopped."
                )
            return dict(self.sample)

    def stationary_capture(self):
        """Require a newly captured image after acknowledged physical zero command."""
        if self.disarmed_at is None:
            raise AssistantError(
                "SEARCH_STOP_UNACKNOWLEDGED", "Capture requires an acknowledged disarm."
            )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            sample = self.latest()
            if datetime.fromisoformat(sample["captured_at"]) > self.disarmed_at:
                return sample
            time.sleep(0.02)
        raise AssistantError(
            "SEARCH_CAMERA_STALE", "No new capture after acknowledged zero motion."
        )

    def drive(self, forward, turn):
        self.check()
        with self.lock:
            self.intent = (float(np.clip(forward, -1, 1)), float(np.clip(turn, -1, 1)))
            self.intent_until = time.monotonic() + self.cfg.intent_lifetime_s

    def stationary(self):
        self.drive(0, 0)

    def disarm(self):
        self.check()
        with self.send_lock:
            self.disarming.set()
            self.socket.send(json.dumps({"type": "search_disarm"}))
        if not self.disarmed.wait(2):
            self.check()
            raise AssistantError(
                "SEARCH_STOP_UNACKNOWLEDGED",
                "Host did not acknowledge the stationary inference boundary.",
            )
        self.check()

    def close(self):
        self.closed.set()
        self.socket.close()
        for thread in self.threads:
            thread.join(timeout=2)
        self.http.close()
