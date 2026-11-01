"""Disposable full app with an authored rendered camera; no hardware connection."""

from dataclasses import replace
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4

import numpy as np
import uvicorn

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import build_library
from teach_and_find.mobile.api import create_app
from teach_and_find.mobile.runtime import OperatorRuntime
from teach_and_find.planner import StationNode, TopologicalGraph
from teach_and_find.sim.world3d import (
    SimulatedLabWorld,
    PlacedObject,
    build_object_catalog,
    render_teaching_views,
)
from teach_and_find.storage import EvidenceStore


def main():
    base = Path(os.environ["PUPPYPI_STREAM_RUN"]).resolve()
    base.mkdir(parents=True, exist_ok=True)
    cfg = Settings()
    cfg = replace(
        cfg,
        assistant=replace(cfg.assistant, data_dir=str(base / "state")),
        mobile=replace(
            cfg.mobile,
            pairing_token="synthetic-stream-acceptance",
            allow_physical_motion=False,
        ),
        tracking=replace(cfg.tracking, enabled=True),
        vision=replace(cfg.vision, enabled=True),
    )
    graph = TopologicalGraph()
    graph.add_node(StationNode("station", 1, (0, 2.25)))
    world = SimulatedLabWorld(graph, cfg.camera)
    catalog = build_object_catalog()
    with EvidenceStore(cfg.assistant.data_dir) as store:
        library = build_library(store, cfg)
        if not library.list():
            refs = [
                image
                for _, image in render_teaching_views(
                    catalog["secret_box_1"], cfg.camera, angles_deg=(-60, 0, 60)
                )
            ]
            library.teach("Red patterned box", refs)

    class Camera:
        mode = "synthetic"

        def __init__(self):
            self.session = str(uuid4())
            self.sequence = 0
            self.started = time.monotonic()

        def read_frame(self):
            self.sequence += 1
            t = time.monotonic() - self.started
            placed = [
                PlacedObject(
                    catalog[k], "station", (x + 0.035 * math.sin(t / 4), 2.0), -90
                )
                for k, x in zip(
                    ["secret_box_1", "blue_tool_case", "emerald_med_kit"],
                    [-0.26, 0.02, 0.29],
                )
            ]
            world.place_station_objects(placed)
            image = world.render_camera(
                0, 1.15, 90, pitch_rad=np.deg2rad(-10), noise_std=0
            )
            now = time.time()
            mono = time.monotonic()
            fid = f"stream-{self.session}-{self.sequence}"
            with (base / "camera-captures.jsonl").open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "frame_id": fid,
                            "capture_unix_ms": now * 1000,
                            "sequence": self.sequence,
                        }
                    )
                    + "\n"
                )
            return CameraFrame(
                image,
                fid,
                datetime.fromtimestamp(now, timezone.utc).isoformat(),
                mono,
                0,
                True,
                {
                    "camera_id": "authored-render-camera",
                    "session_id": self.session,
                    "sequence": self.sequence,
                    "calibration_id": "authored-render-intrinsics-v1",
                    "capture_time_basis": "host_render_completion_clock",
                    "cross_device_clock_synchronized": False,
                    "clock_uncertainty_s": 0,
                    "source": "authored_pinhole_renderer_not_physics_or_physical_camera",
                },
            )

        def send_command(self, command):
            raise RuntimeError("Benchmark does not actuate even synthetic motion.")

        def close(self):
            pass

    runtime = OperatorRuntime(cfg, device=Camera())
    app = create_app(cfg, runtime=runtime)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.getenv("PUPPYPI_STREAM_PORT", "18770")),
        access_log=False,
    )


if __name__ == "__main__":
    main()
