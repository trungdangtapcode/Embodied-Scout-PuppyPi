"""Synthetic and explicitly selected TCP robot adapters for the operator console."""

from __future__ import annotations

import math
from dataclasses import replace
import threading
import time
from typing import Protocol
from uuid import uuid4

import numpy as np

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.edge_client import RemotePuppyPiClient
from teach_and_find.library import utc_now
from teach_and_find.mission import PuppyActionCommand
from teach_and_find.planner import StationNode, TopologicalGraph
from teach_and_find.sim.world3d import (
    PlacedObject,
    SimulatedLabWorld,
    build_object_catalog,
)


class RobotDevice(Protocol):
    mode: str

    def read_frame(self) -> CameraFrame | None: ...
    def send_command(self, command: PuppyActionCommand) -> None: ...
    def close(self) -> None: ...


class MockRobot:
    """Kinematic rendered preview; never describe its state as physical telemetry."""

    mode = "synthetic"

    def __init__(self, settings: Settings):
        graph = TopologicalGraph()
        graph.add_node(StationNode("Station_A", 1, (0.0, 2.25)))
        self.world = SimulatedLabWorld(graph, camera=settings.camera)
        catalog = build_object_catalog()
        self.world.place_station_objects(
            [
                PlacedObject(catalog[key], "Station_A", (x, 2.0), -90)
                for key, x in (
                    ("secret_box_1", 0.0),
                    ("blue_tool_case", -0.30),
                    ("emerald_med_kit", 0.30),
                )
            ]
        )
        self.pose = [0.0, 1.25, 90.0]
        self.lock = threading.Lock()
        self.session = str(uuid4())
        self.sequence = 0
        self.last_command = time.monotonic()
        self.closed = False

    def read_frame(self) -> CameraFrame:
        with self.lock:
            pose = tuple(self.pose)
        captured = utc_now()
        stamp = time.monotonic()
        image = self.world.render_camera(
            *pose,
            pitch_rad=math.radians(-10),
            noise_std=0,
            rng=np.random.default_rng(7),
        )
        self.sequence += 1
        return CameraFrame(
            image,
            f"{self.session}:{self.sequence}",
            captured,
            stamp,
            0.0,
            True,
            {
                "camera_id": "synthetic_robot_rgb",
                "session_id": self.session,
                "sequence": self.sequence,
                "capture_time_basis": "synthetic_render_time",
                "calibration_id": "synthetic_camera_settings",
                "source": "pinhole_renderer",
            },
        )

    def send_command(self, command: PuppyActionCommand) -> None:
        with self.lock:
            now = time.monotonic()
            dt = min(0.2, now - self.last_command)
            self.last_command = now
            angle = math.radians(self.pose[2])
            self.pose[0] = max(
                -0.7,
                min(0.7, self.pose[0] + math.cos(angle) * command.vx_cm_s * dt / 100),
            )
            self.pose[1] = max(
                0.4,
                min(1.6, self.pose[1] + math.sin(angle) * command.vx_cm_s * dt / 100),
            )
            self.pose[2] += math.degrees(command.yaw_rate_rad_s) * dt

    def close(self) -> None:
        self.closed = True


class RelayRobot:
    """Separate frame/control sockets keep image reads off the stop-command path."""

    mode = "physical"

    def __init__(self, settings: Settings):
        self.settings = replace(
            settings,
            edge_relay=replace(
                settings.edge_relay,
                socket_timeout_s=settings.mobile.transport_timeout_s,
            ),
        )
        self.frames: RemotePuppyPiClient | None = None
        self.commands: RemotePuppyPiClient | None = None
        self.closed = False

    def read_frame(self) -> CameraFrame | None:
        try:
            if self.frames is None:
                self.frames = RemotePuppyPiClient(self.settings)
            return self.frames.get_frame_sample()
        except (OSError, ValueError, RuntimeError):
            if self.frames:
                self.frames.close(stop_motion=False)
                self.frames = None
            raise

    def send_command(self, command: PuppyActionCommand) -> None:
        try:
            if self.commands is None:
                self.commands = RemotePuppyPiClient(self.settings)
            self.commands.send_action(command)
        except (OSError, ValueError, RuntimeError):
            if self.commands:
                self.commands.close(stop_motion=False)
                self.commands = None
            raise

    def close(self) -> None:
        for client in (self.commands, self.frames):
            if client:
                client.close(stop_motion=False)
        self.commands = self.frames = None
        self.closed = True
