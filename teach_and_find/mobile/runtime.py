"""Independent camera and command workers shared by every mobile session."""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import asdict
import threading
import time
from uuid import uuid4

import cv2

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.control import ControlGate
from teach_and_find.library import utc_now
from teach_and_find.mission import PuppyActionCommand
from teach_and_find.mobile.devices import MockRobot, RelayRobot, RobotDevice
from teach_and_find.storage import AssistantError


class OperatorRuntime:
    def __init__(self, settings: Settings, device: RobotDevice | None = None):
        self.settings = settings
        if device is not None:
            self.device = device
        elif settings.mobile.robot_mode == "mock":
            self.device = MockRobot(settings)
        elif settings.mobile.robot_mode == "relay":
            self.device = RelayRobot(settings)
        else:
            raise AssistantError(
                "UNKNOWN_ROBOT_BACKEND",
                "Unsupported robot backend; no substitute adapter is selected.",
            )
        self.gate = ControlGate(settings)
        self.lock = threading.RLock()
        self.frames: OrderedDict[str, tuple[CameraFrame, bytes]] = OrderedDict()
        self.events: deque[dict] = deque(maxlen=settings.mobile.event_limit)
        self.latest: CameraFrame | None = None
        self.connected = False
        self.error: str | None = None
        self.last_ack_at: str | None = None
        self.last_sent = self.gate.command
        self.stop_event = threading.Event()
        self.wake_control = threading.Event()
        self.threads: list[threading.Thread] = []
        self.tracking_feed = None
        if settings.tracking.enabled:
            from teach_and_find.tracking_service import TrackingFeed

            self.tracking_feed = TrackingFeed(settings)
        self.event("console_ready", "Operator console initialized.")

    @property
    def motion_enabled(self) -> bool:
        return (
            self.device.mode == "synthetic"
            or self.settings.mobile.allow_physical_motion
        )

    def event(self, kind: str, message: str) -> None:
        with self.lock:
            self.events.appendleft(
                {"id": str(uuid4()), "at": utc_now(), "kind": kind, "message": message}
            )

    def frame_window(self, frame_id: str) -> list[CameraFrame]:
        """Freeze a bounded same-session window ending at the displayed fresh frame."""
        with self.lock:
            end, _ = self.frame(frame_id, require_fresh=True)
            candidates = []
            for sample, _ in self.frames.values():
                if (
                    sample.provenance.get("camera_id"),
                    sample.provenance.get("session_id"),
                ) == (
                    end.provenance.get("camera_id"),
                    end.provenance.get("session_id"),
                ):
                    candidates.append(sample)
                if sample.frame_id == frame_id:
                    break
            return candidates[-self.settings.vision.max_frames :]

    def start(self) -> None:
        if self.tracking_feed:
            self.tracking_feed.start()
        for target in (self._camera_loop, self._control_loop):
            thread = threading.Thread(target=target, daemon=True)
            self.threads.append(thread)
            thread.start()

    def _fresh(self, frame: CameraFrame | None) -> bool:
        return bool(
            frame
            and frame.freshness_verified
            and frame.age() <= self.settings.mobile.max_frame_age_s
        )

    def _ready(self) -> bool:
        return self.motion_enabled and self.connected and self._fresh(self.latest)

    def frame(
        self, frame_id: str | None = None, *, require_fresh: bool = False
    ) -> tuple[CameraFrame, bytes]:
        with self.lock:
            frame_id = frame_id or (self.latest.frame_id if self.latest else "")
            if frame_id not in self.frames:
                raise AssistantError(
                    "FRAME_UNAVAILABLE", "The camera frame is no longer available."
                )
            result = self.frames[frame_id]
            if require_fresh and not self._fresh(result[0]):
                raise AssistantError(
                    "STALE_FRAME", "A fresh, timestamped displayed frame is required."
                )
            return result

    def _camera_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                sample = self.device.read_frame()
                if sample is None:
                    raise ValueError("No camera frame.")
                ok, encoded = cv2.imencode(
                    ".jpg",
                    sample.image,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self.settings.mobile.jpeg_quality],
                )
                if not ok:
                    raise ValueError("Cannot encode camera frame.")
                with self.lock:
                    self.frames[sample.frame_id] = (sample, encoded.tobytes())
                    while len(self.frames) > self.settings.mobile.frame_buffer_size:
                        self.frames.popitem(last=False)
                    self.latest = sample
                    if not self.connected:
                        self.event(
                            "camera_connected",
                            "Camera connected; controls remain disarmed.",
                        )
                    self.connected = True
                    self.error = None
                if self.tracking_feed:
                    self.tracking_feed.offer(sample)
            except (OSError, ValueError, RuntimeError) as error:
                with self.lock:
                    if self.connected:
                        self.event(
                            "camera_disconnected",
                            "Camera unavailable; controls disarmed.",
                        )
                    self.connected = False
                    self.error = type(error).__name__
                    self.gate.stop("camera_disconnected")
                self.wake_control.set()
            self.stop_event.wait(self.settings.mobile.frame_poll_s)

    def _control_loop(self) -> None:
        attempted = False
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    previous = self.gate.owner
                    command = self.gate.tick(ready=self._ready())
                    if previous and not self.gate.owner:
                        self.event("control_stopped", self.gate.reason)
                    # Monitoring alone never opens a command socket.
                    should_send = self.motion_enabled and (
                        self.gate.owner is not None or attempted
                    )
                if should_send:
                    try:
                        self.device.send_command(command)
                        with self.lock:
                            self.last_sent = command
                            self.last_ack_at = utc_now()
                        # A stop can arrive while the transport is sending. Ensure
                        # the next iteration still transmits zero in that case.
                        attempted = bool(
                            command.vx_cm_s
                            or command.vy_cm_s
                            or command.yaw_rate_rad_s
                            or self.gate.owner
                        )
                    except (OSError, ValueError, RuntimeError):
                        with self.lock:
                            self.gate.stop("command_connection_lost")
                            self.last_ack_at = None
                            self.event(
                                "control_stopped",
                                "Command connection lost; no automatic resume.",
                            )
                        attempted = False
                self.wake_control.wait(self.settings.mobile.control_tick_s)
                self.wake_control.clear()
        finally:
            if attempted:
                try:
                    self.device.send_command(
                        PuppyActionCommand.clamped(self.settings.motion)
                    )
                except (OSError, ValueError, RuntimeError):
                    pass

    def arm(self, owner: str, challenge: str, frame_id: str) -> dict:
        with self.lock:
            if self.tracking_feed:
                from teach_and_find.storage import EvidenceStore
                from teach_and_find.tracking_service import ACTIVE

                with EvidenceStore(self.settings.assistant.data_dir) as store:
                    if store.db.execute(
                        "SELECT 1 FROM tracking_sessions WHERE status IN (?,?,?,?,?)",
                        ACTIVE,
                    ).fetchone():
                        raise AssistantError(
                            "TRACKING_STATIONARY_ONLY",
                            "Stop tracking before arming motion.",
                        )
            self.frame(frame_id, require_fresh=True)
            epoch = self.gate.arm(owner, challenge, ready=self._ready())
            self.event("control_armed", "Manual control session acquired.")
            self.wake_control.set()
            return {"epoch": epoch, "lease_s": self.settings.mobile.command_lease_s}

    def drive(self, owner: str, payload: dict) -> None:
        with self.lock:
            try:
                self.frame(payload["frame_id"], require_fresh=True)
                self.gate.drive(
                    owner,
                    payload["epoch"],
                    payload["sequence"],
                    payload["challenge"],
                    payload["forward"],
                    payload["turn"],
                    ready=self._ready(),
                )
            except AssistantError:
                if self.gate.owner == owner:
                    self.gate.stop("invalid_or_stale_command")
                self.wake_control.set()
                raise
        self.wake_control.set()

    def stop(self, reason: str = "operator_stop") -> None:
        with self.lock:
            self.gate.stop(reason)
            self.event("control_stopped", reason)
        self.wake_control.set()

    def disconnect(self, owner: str) -> None:
        with self.lock:
            if self.gate.owner == owner:
                self.stop("operator_disconnected")

    def status(self, owner: str | None = None) -> dict:
        with self.lock:
            frame = self.latest
            return {
                "schema_version": 1,
                "server_time": utc_now(),
                "mode": self.device.mode,
                "connected": self.connected,
                "error": self.error,
                "camera": {
                    "available": self.connected and frame is not None,
                    "frame_id": frame.frame_id if frame else None,
                    "captured_at": frame.captured_at if frame else None,
                    "age_s": frame.age() if frame else None,
                    "freshness_verified": bool(frame and frame.freshness_verified),
                    "fresh": self._fresh(frame),
                    "provenance": frame.provenance if frame else {},
                },
                "control": {
                    "enabled": self.motion_enabled,
                    "ready": self._ready(),
                    "armed": self.gate.owner is not None,
                    "owned": self.gate.owner == owner and owner is not None,
                    "reason": self.gate.reason,
                    "challenge": self.gate.challenge(),
                    "command": asdict(self.gate.command),
                    "last_ack_at": self.last_ack_at,
                    "ack_meaning": "accepted_by_adapter_not_measured_motion",
                    "lease_s": self.settings.mobile.command_lease_s,
                },
                "telemetry": {
                    "battery_percent": None,
                    "measured_pose": None,
                    "reason": "not_provided_by_current_adapter",
                },
                "events": list(self.events)[:20],
            }

    def close(self) -> None:
        self.stop("server_shutdown")
        self.stop_event.set()
        self.wake_control.set()
        for thread in self.threads:
            thread.join(timeout=3.0)
        if self.tracking_feed:
            self.tracking_feed.close()
        self.device.close()
