#!/usr/bin/env python3
"""Zero-dependency single-file ROS 2 TCP relay for Hiwonder PuppyPi Standard.

Copy ONLY this single file into Hiwonder's preinstalled ROS 2 container on
PuppyPi's Raspberry Pi and run:
    python3 puppypi_edge_relay.py --port 18765

For offline loopback testing on a workstation without ROS 2:
    python3 scripts/puppypi_edge_relay.py --mock --port 18765
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import threading
import time
from typing import Any, Callable

import cv2
import numpy as np


def _recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed by peer.")
        buf.extend(chunk)
    return bytes(buf)


class EdgeRelayServer:
    """Length-prefixed TCP server streaming JPEG frames & forwarding ROS commands."""

    def __init__(
        self,
        get_frame_fn: Callable[[], np.ndarray | None],
        apply_cmd_fn: Callable[[dict[str, Any]], None],
        halt_fn: Callable[[], None],
        host: str = "0.0.0.0",
        port: int = 18765,
        jpeg_quality: int = 85,
        watchdog_timeout_s: float = 0.30,
    ) -> None:
        self.get_frame_fn = get_frame_fn
        self.apply_cmd_fn = apply_cmd_fn
        self.halt_fn = halt_fn
        self.host = host
        self.port = port
        self.jpeg_quality = jpeg_quality
        self.watchdog_timeout_s = watchdog_timeout_s

        self._stop_evt = threading.Event()
        self._last_cmd_ts = 0.0
        self._moving = False
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self.bound_port: int = int(self._sock.getsockname()[1])

    def start(self) -> None:
        self._sock.listen(2)
        self._sock.settimeout(0.25)
        threading.Thread(target=self._watchdog_loop, daemon=True).start()
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop_evt.set()
        try:
            self._sock.close()
        except OSError:
            pass

    def _watchdog_loop(self) -> None:
        while not self._stop_evt.is_set():
            time.sleep(0.05)
            with self._lock:
                expired = self._moving and (time.monotonic() - self._last_cmd_ts > self.watchdog_timeout_s)
                if expired:
                    self._moving = False
            if expired:
                self.halt_fn()

    def _accept_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            while not self._stop_evt.is_set():
                try:
                    op = _recv_exact(conn, 1)
                    if op == b"F":
                        frame = self.get_frame_fn()
                        if frame is None:
                            conn.sendall(struct.pack("!I", 0))
                        else:
                            ok, enc = cv2.imencode(
                                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
                            )
                            data = enc.tobytes() if ok else b""
                            conn.sendall(struct.pack("!I", len(data)) + data)
                    elif op == b"C":
                        (length,) = struct.unpack("!I", _recv_exact(conn, 4))
                        payload = json.loads(_recv_exact(conn, length).decode("utf-8"))
                        self.apply_cmd_fn(payload)
                        vel = payload.get("velocity_fields", {})
                        nonzero = any(abs(float(vel.get(k, 0.0))) > 1e-4 for k in ("x", "y", "yaw_rate"))
                        with self._lock:
                            self._last_cmd_ts = time.monotonic()
                            self._moving = nonzero
                        conn.sendall(b"O")
                except (ConnectionError, OSError):
                    self.halt_fn()
                    break


def _run_ros2_mode(host: str, port: int, image_topic: str) -> None:
    import rclpy
    from cv_bridge import CvBridge
    from puppy_control_msgs.msg import Gait, Pose, Velocity
    from rclpy.node import Node
    from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import Image

    rclpy.init()
    node = Node("puppypi_edge_relay")
    bridge = CvBridge()
    lock = threading.Lock()
    latest: list[np.ndarray | None] = [None]

    qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1)
    vel_pub = node.create_publisher(Velocity, "/puppy_control/velocity", 10)
    vel_move_pub = node.create_publisher(Velocity, "/puppy_control/velocity_move", 10)
    pose_pub = node.create_publisher(Pose, "/puppy_control/pose", 10)
    gait_pub = node.create_publisher(Gait, "/puppy_control/gait", 10)

    def on_img(msg: Any) -> None:
        img = np.asarray(bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8"), dtype=np.uint8)
        with lock:
            latest[0] = img

    node.create_subscription(Image, image_topic, on_img, qos)

    def get_frame() -> np.ndarray | None:
        with lock:
            return None if latest[0] is None else latest[0].copy()

    def apply_cmd(p: dict[str, Any]) -> None:
        v = Velocity(**p["velocity_fields"])
        (vel_move_pub if p["velocity_topic"].endswith("velocity_move") else vel_pub).publish(v)
        pose_pub.publish(Pose(**p["pose_fields"]))
        if p.get("gait_fields"):
            gait_pub.publish(Gait(**p["gait_fields"]))

    def halt() -> None:
        vel_pub.publish(Velocity(x=0.0, y=0.0, yaw_rate=0.0))

    srv = EdgeRelayServer(get_frame, apply_cmd, halt, host=host, port=port)
    srv.start()
    node.get_logger().info(f"Edge relay listening on {host}:{srv.bound_port}")
    try:
        rclpy.spin(node)
    finally:
        halt()
        srv.stop()
        rclpy.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(description="PuppyPi Standard ROS 2 Edge Relay")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--image-topic", default="/image_raw")
    ap.add_argument("--mock", action="store_true", help="Run synthetic camera mock without ROS 2")
    args = ap.parse_args()

    if args.mock:
        dummy = np.full((480, 640, 3), 180, dtype=np.uint8)
        srv = EdgeRelayServer(lambda: dummy, lambda p: None, lambda: None, host=args.host, port=args.port)
        srv.start()
        print(f"Mock PuppyPi relay listening on {args.host}:{srv.bound_port} (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            srv.stop()
    else:
        _run_ros2_mode(args.host, args.port, args.image_topic)


if __name__ == "__main__":
    main()
