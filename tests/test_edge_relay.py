"""Loopback test verifying portable Sim-to-Real TCP Edge Relay + Watchdog."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

import numpy as np

from teach_and_find.apriltag_pose import AprilTagPoseEstimator
from teach_and_find.config import Settings
from teach_and_find.edge_client import RemotePuppyPiClient
from teach_and_find.mission import PuppyActionCommand


def _load_relay_module() -> Any:
    relay_path = Path(__file__).resolve().parents[1] / "scripts" / "puppypi_edge_relay.py"
    spec = importlib.util.spec_from_file_location("puppypi_edge_relay", relay_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_edge_relay_frame_command_and_watchdog() -> None:
    relay_mod = _load_relay_module()
    cfg = Settings()
    est = AprilTagPoseEstimator(cfg.camera, cfg.apriltag)

    # Create a camera frame containing AprilTag #1 to verify JPEG fidelity
    canvas = np.full((480, 640, 3), 210, dtype=np.uint8)
    tag_img = est.generate_tag_image(tag_id=1, side_px=160, border_px=20)
    canvas[140:340, 220:420] = tag_img

    received_cmds: list[dict[str, Any]] = []
    halt_count = [0]

    srv = relay_mod.EdgeRelayServer(
        get_frame_fn=lambda: canvas,
        apply_cmd_fn=lambda payload: received_cmds.append(payload),
        halt_fn=lambda: halt_count.__setitem__(0, halt_count[0] + 1),
        host="127.0.0.1",
        port=0,
        watchdog_timeout_s=0.12,
    )
    srv.start()
    try:
        client = RemotePuppyPiClient(cfg, host="127.0.0.1", port=srv.bound_port)
        frame = client.get_frame()
        assert frame is not None and frame.shape == (480, 640, 3)

        # AprilTag #1 must survive JPEG compression over the relay
        detections = est.detect(frame)
        assert len(detections) == 1 and detections[0].tag_id == 1

        # Lateral strafe command must route to /puppy_control/velocity_move
        cmd = PuppyActionCommand.clamped(cfg.motion, vx_cm_s=0.0, vy_cm_s=6.0)
        client.send_action(cmd, include_gait=True)
        assert len(received_cmds) == 1
        assert received_cmds[0]["velocity_topic"] == "/puppy_control/velocity_move"
        assert received_cmds[0]["pose_fields"]["yaw"] == 0.0

        # Wait past 120ms watchdog window without sending new commands -> auto-halt must fire!
        time.sleep(0.22)
        assert halt_count[0] >= 1

        client.close()
    finally:
        srv.stop()
