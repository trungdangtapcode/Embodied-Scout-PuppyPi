"""Host .venv TCP client talking to scripts/puppypi_edge_relay.py on PuppyPi."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json
import math
import socket
import struct
import time

import cv2
import numpy as np

from teach_and_find.config import Settings
from teach_and_find.camera import CameraFrame
from teach_and_find.mission import PuppyActionCommand
from teach_and_find.ros2_bridge import PublishedRosCommand, translate_action_to_ros_payload


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Edge relay connection closed.")
        buf.extend(chunk)
    return bytes(buf)


class RemotePuppyPiClient:
    """Portable offboard client for streaming camera frames & sending safe actions."""

    def __init__(
        self,
        settings: Settings | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.cfg = settings or Settings()
        self.host = host or self.cfg.edge_relay.host
        self.port = port if port is not None else self.cfg.edge_relay.port
        self._sock = socket.create_connection(
            (self.host, self.port),
            timeout=self.cfg.edge_relay.socket_timeout_s,
        )
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def get_frame(self) -> np.ndarray | None:
        """Fetch and decode the latest 640x480 BGR camera frame from PuppyPi."""
        self._sock.sendall(b"F")
        (length,) = struct.unpack("!I", _recv_exact(self._sock, 4))
        if length == 0:
            return None
        jpg_bytes = _recv_exact(self._sock, length)
        arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def send_action(self, cmd: PuppyActionCommand, include_gait: bool = False) -> PublishedRosCommand:
        """Translate PuppyActionCommand to ROS 2 fields and transmit over TCP."""
        ros_cmd = translate_action_to_ros_payload(cmd, self.cfg, include_gait=include_gait)
        body = json.dumps(dataclasses.asdict(ros_cmd)).encode("utf-8")
        self._sock.sendall(b"C" + struct.pack("!I", len(body)) + body)
        ack = _recv_exact(self._sock, 1)
        if ack != b"O":
            raise RuntimeError("Unexpected ACK from PuppyPi edge relay.")
        return ros_cmd

    def get_frame_sample(self) -> CameraFrame | None:
        """Request v2 image metadata; legacy relays must be upgraded for this API.

        Relay-local frame age plus the full round-trip time is a conservative age
        estimate. The UTC capture time is an estimate on the host clock, not an
        assertion that two device clocks have been synchronized.
        """
        started = time.monotonic()
        self._sock.sendall(b"M")
        (metadata_size,) = struct.unpack("!I", _recv_exact(self._sock, 4))
        if metadata_size > 16384:
            raise ValueError("Oversized relay metadata.")
        metadata = json.loads(_recv_exact(self._sock, metadata_size))
        if not isinstance(metadata, dict):
            raise ValueError("Relay metadata must be an object.")
        (size,) = struct.unpack("!I", _recv_exact(self._sock, 4))
        if size > 8 * 1024 * 1024:
            raise ValueError("Oversized relay frame.")
        payload = _recv_exact(self._sock, size)
        received = time.monotonic()
        if not payload:
            return None
        image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or metadata.get("schema_version") != 2:
            raise ValueError("Invalid relay frame or metadata version.")
        reported_age = metadata.get("age_s")
        verified = (metadata.get("freshness_verified") is True
                    and isinstance(reported_age, (float, int))
                    and math.isfinite(reported_age) and 0 <= reported_age < 86400)
        age = float(reported_age) + received - started if verified else 0.0
        captured_at = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(timespec="microseconds")
        provenance = {**metadata, "transport_rtt_s": received - started,
                      "capture_time_basis": "host_receive_minus_conservative_age" if verified else "host_receive_only",
                      "cross_device_clock_synchronized": False}
        return CameraFrame(image, f"{metadata.get('session_id')}:{metadata.get('sequence')}",
                           captured_at, received, age, verified, provenance)

    def stop_motion(self) -> None:
        """Send an immediate zero-velocity command before disconnecting."""
        self.send_action(PuppyActionCommand.clamped(self.cfg.motion))

    def close(self, *, stop_motion: bool = True) -> None:
        try:
            if stop_motion:
                self.stop_motion()
        except (OSError, RuntimeError):
            pass
        self._sock.close()

    def __enter__(self) -> RemotePuppyPiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
