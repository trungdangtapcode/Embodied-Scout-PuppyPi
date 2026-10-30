"""Host .venv TCP client talking to scripts/puppypi_edge_relay.py on PuppyPi."""

from __future__ import annotations

import dataclasses
import json
import socket
import struct

import cv2
import numpy as np

from teach_and_find.config import Settings
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

    def stop_motion(self) -> None:
        """Send an immediate zero-velocity command before disconnecting."""
        self.send_action(PuppyActionCommand.clamped(self.cfg.motion))

    def close(self) -> None:
        try:
            self.stop_motion()
        except OSError:
            pass
        self._sock.close()

    def __enter__(self) -> RemotePuppyPiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
