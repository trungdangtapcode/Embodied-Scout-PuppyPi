"""Explicit kinematic search fixture: bounded velocity integration, no oracle API.

Only the renderer owns authored object placement and true camera pose. The search
worker receives images and separately registered landmark/map calibration.
"""

from __future__ import annotations

import math
from dataclasses import replace
from collections import deque
import threading
import time
from uuid import uuid4

import numpy as np

from teach_and_find.camera import CameraFrame
from teach_and_find.library import utc_now
from teach_and_find.planner import StationNode, TopologicalGraph
from teach_and_find.sim.world3d import (
    PlacedObject,
    SimulatedLabWorld,
    build_object_catalog,
)


LANDMARKS = [
    (1, -0.45, 2.35),
    (2, 0.45, 2.35),
    (3, -1.5, 0.4),
    (4, -1.5, 1.6),
    (5, 1.5, 0.4),
    (6, 1.5, 1.6),
    (7, -1.2, 2.35),
    (8, 1.2, 2.35),
    (9, -1.5, 2.7),
    (10, -0.9, 2.7),
    (11, 0.0, 2.7),
    (12, 0.9, 2.7),
    (13, 1.5, 2.7),
    (14, -2.0, 1.0),
    (15, -2.0, 2.0),
    (16, 2.0, 1.0),
    (17, 2.0, 2.0),
]
MARKER_CENTER_HEIGHT_M = 0.26
MARKER_SIZE_M = 0.18


def hidden_side_decoy(catalog):
    """Authored evaluation asset: identical target front, different side textures."""
    return replace(
        catalog["secret_box_1"],
        object_id="hidden_side_decoy",
        display_name="Hidden-side decoy",
        face_textures={
            **catalog["secret_box_1"].face_textures,
            **{
                side: catalog["lookalike_red_box"].face_textures[side]
                for side in ("left", "right", "back")
            },
        },
    )


def fixture_calibration():
    """Authored simulator calibration. Contains no target identity/placement."""
    landmarks = {}
    for identifier, x, y in LANDMARKS:
        normal = np.array([-x, -y, 0.0])
        normal /= np.linalg.norm(normal)
        right = np.array([-normal[1], normal[0], 0.0])
        center = np.array([x, y, MARKER_CENTER_HEIGHT_M]) + 0.003 * normal
        up = np.array([0.0, 0.0, 1.0])
        corners = [
            center + a * (MARKER_SIZE_M / 2) * right + b * (MARKER_SIZE_M / 2) * up
            for a, b in [(-1, 1), (1, 1), (1, -1), (-1, -1)]
        ]
        landmarks[str(identifier)] = {"corners": [p.tolist() for p in corners]}
    return {
        "id": "authored-search-lab-v8",
        "method": "authored_known_map_not_learned",
        "bounds": [-1.1, 1.1, 0.3, 2.7],
        "obstacles": [[x, 1.9] for x in np.arange(-0.8, 0.81, 0.05)],
        "landmarks": landmarks,
        "stations": [
            {
                "id": "Station_A",
                "center": [-0.3, 2.0],
                "radius_m": 0.24,
                "goals": [
                    [-0.8, 1.65, math.radians(35)],
                    [0.2, 1.65, math.radians(145)],
                ],
            },
            {
                "id": "Station_B",
                "center": [0.3, 2.0],
                "radius_m": 0.24,
                "goals": [
                    [-0.2, 1.65, math.radians(35)],
                    [0.8, 1.65, math.radians(145)],
                ],
            },
        ],
    }


class SearchSimRobot:
    mode = "synthetic"

    def __init__(self, settings):
        self.settings = settings
        self._calibration = fixture_calibration()
        graph = TopologicalGraph()
        for identifier, x, y in LANDMARKS:
            graph.add_node(StationNode(f"Landmark_{identifier}", identifier, (x, y)))
        self.world = SimulatedLabWorld(
            graph,
            camera=settings.camera,
            tag_size_m=MARKER_SIZE_M,
            tag_center_height_m=MARKER_CENTER_HEIGHT_M,
        )
        catalog = build_object_catalog()
        catalog["hidden_side_decoy"] = hidden_side_decoy(catalog)
        # Scenario is an explicit fixture selection, consumed only by the renderer.
        scenario = settings.search_sim.scenario
        choices = {
            "target": [
                ("secret_box_1", "Station_A", -0.3),
                ("lookalike_red_box", "Station_B", 0.3),
            ],
            "duplicates": [
                ("secret_box_1", "Station_A", -0.3),
                ("secret_box_1", "Station_B", 0.3),
            ],
            "hidden": [
                ("secret_box_1", "Station_A", -0.3),
                ("hidden_side_decoy", "Station_B", 0.3),
            ],
            "decoy": [("lookalike_red_box", "Station_A", -0.3)],
            "hidden_absent": [("hidden_side_decoy", "Station_A", -0.3)],
            "relocated": [
                ("lookalike_red_box", "Station_A", -0.3),
                ("secret_box_1", "Station_B", 0.3),
            ],
            "absent": [("blue_tool_case", "Station_B", 0.3)],
            "empty": [],
        }
        if scenario not in choices:
            raise ValueError("Unknown search simulator scenario; no substitute.")
        rng = np.random.default_rng(settings.search_sim.seed)
        objects = []
        for key, station, x in choices[scenario]:
            dx, dy, yaw = (
                (
                    rng.uniform(-0.06, 0.06),
                    rng.uniform(-0.025, 0.025),
                    rng.uniform(-12, 12),
                )
                if settings.search_sim.seed
                else (0.0, 0.0, 0.0)
            )
            objects.append(
                PlacedObject(catalog[key], station, (x + dx, 2.0 + dy), -90 + yaw)
            )
        self.world.place_station_objects(objects)
        self._pose = [0.0, 1.0, 90.0]
        self._lock = threading.Lock()
        self._last_tick = time.monotonic()
        self._session, self._sequence = str(uuid4()), 0
        self.closed = False
        self.evaluation_enabled = False
        self.evaluation_trajectory = deque(maxlen=20000)
        self.evaluation_frames = deque(maxlen=10000)
        self.evaluation_collisions = 0
        self.evaluation_collision_method = (
            "known_map_footprint_command_integration_v1_not_physics"
        )

    def send_command(self, command):
        with self._lock:
            now = time.monotonic()
            dt = min(0.12, now - self._last_tick)
            self._last_tick = now
            angle = math.radians(self._pose[2])
            x = self._pose[0] + math.cos(angle) * command.vx_cm_s / 100 * dt
            y = self._pose[1] + math.sin(angle) * command.vx_cm_s / 100 * dt
            x0, x1, y0, y1 = self._calibration["bounds"]
            radius = self.settings.search.footprint_radius_m
            collision = not (
                x0 + radius < x < x1 - radius and y0 + radius < y < y1 - radius
            )
            collision = collision or any(
                math.dist([x, y], point) <= radius
                for point in self._calibration["obstacles"]
            )
            if not collision:
                self._pose[:2] = [x, y]
            elif self.evaluation_enabled and command.vx_cm_s != 0:
                self.evaluation_collisions += 1
            self._pose[2] += math.degrees(command.yaw_rate_rad_s) * dt
            if self.evaluation_enabled:
                self.evaluation_trajectory.append(
                    {
                        "at": now,
                        "pose": list(self._pose),
                        "command": [command.vx_cm_s, command.yaw_rate_rad_s],
                    }
                )

    def read_frame(self):
        with self._lock:
            pose = tuple(self._pose)
        captured, stamp = utc_now(), time.monotonic()
        image = self.world.render_camera(
            *pose,
            pitch_rad=self.settings.camera.default_pitch_rad,
            noise_std=0,
            rng=np.random.default_rng(7),
        )
        self._sequence += 1
        if self.evaluation_enabled:
            self.evaluation_frames.append(
                {
                    "frame_id": f"{self._session}:{self._sequence}",
                    "captured_at": captured,
                    "pose": list(pose),
                }
            )
        return CameraFrame(
            image,
            f"{self._session}:{self._sequence}",
            captured,
            stamp,
            0.0,
            True,
            {
                "camera_id": "search_sim_rgb",
                "session_id": self._session,
                "sequence": self._sequence,
                "capture_time_basis": "synthetic_render_time",
                "calibration_id": "authored-search-lab-v8",
                "source": "pinhole_renderer_kinematic_velocity_integration",
            },
        )

    def close(self):
        self.closed = True
