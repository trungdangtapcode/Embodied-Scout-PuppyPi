"""Opt-in loopback acceptance server: rendered input, real app/worker/model."""

import os, time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import cv2
import numpy as np
import uvicorn
from teach_and_find.config import Settings
from teach_and_find.camera import CameraFrame
from teach_and_find.library import utc_now
from teach_and_find.mobile.api import create_app
from teach_and_find.mobile.runtime import OperatorRuntime
from teach_and_find.sim.world3d import (
    SimulatedLabWorld,
    PlacedObject,
    build_object_catalog,
)
from teach_and_find.planner import TopologicalGraph, StationNode

base = Path(os.environ["PUPPYPI_MEMORY_ACCEPTANCE_DIR"]).resolve()
base.mkdir(parents=True, exist_ok=True)
cfg = Settings()
cfg = replace(
    cfg,
    assistant=replace(cfg.assistant, data_dir=str(base / "state")),
    memory=replace(cfg.memory, enabled=True),
    mobile=replace(
        cfg.mobile,
        pairing_token="synthetic-memory-acceptance",
        allow_physical_motion=False,
    ),
)
graph = TopologicalGraph()
graph.add_node(StationNode("station", 1, (0.0, 2.25)))
world = SimulatedLabWorld(graph, camera=cfg.camera)
catalog = build_object_catalog()
scenes = [
    ["secret_box_1"],
    ["blue_tool_case"],
    ["emerald_med_kit"],
    ["secret_box_1", "blue_tool_case"],
    ["amber_sensor_cube"],
    ["blue_tool_case", "emerald_med_kit"],
]
for i, objects in enumerate(scenes):
    positions = [0.0] if len(objects) == 1 else [-0.16, 0.16]
    world.place_station_objects(
        [
            PlacedObject(catalog[key], "station", (x, 2.0), -90)
            for key, x in zip(objects, positions)
        ]
    )
    image = world.render_camera(
        0.0,
        1.25,
        90.0,
        pitch_rad=np.deg2rad(-10),
        noise_std=0,
        rng=np.random.default_rng(11),
    )
    cv2.imwrite(str(base / f"scene-{i}.png"), image)
# Explicit occlusion fixture: the entire camera view is covered. Its hidden
# scene truth is never passed to the model. This is not a physical recording.
cv2.imwrite(str(base / "scene-6.png"), np.full((480, 640, 3), 128, np.uint8))
(base / "current-scene.txt").write_text("0")


class ReplayCamera:
    mode = "synthetic"

    def __init__(self):
        self.session = str(uuid4())
        self.sequence = 0
        self.commands = []

    def read_frame(self):
        index = int((base / "current-scene.txt").read_text())
        image = cv2.imread(str(base / f"scene-{index}.png"))
        self.sequence += 1
        return CameraFrame(
            image,
            f"{self.session}:{self.sequence}",
            utc_now(),
            time.monotonic(),
            0.0,
            True,
            {
                "camera_id": "synthetic_replay",
                "session_id": self.session,
                "sequence": self.sequence,
                "fixture_index": index,
                "capture_time_basis": "synthetic_replay_ingest_time",
                "source": "pinhole_renderer_replay",
            },
        )

    def send_command(self, command):
        self.commands.append(command)

    def close(self):
        pass


runtime = OperatorRuntime(cfg, ReplayCamera())
uvicorn.run(
    create_app(cfg, runtime=runtime), host="127.0.0.1", port=18767, access_log=False
)
