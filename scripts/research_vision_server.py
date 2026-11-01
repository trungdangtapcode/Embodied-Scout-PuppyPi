"""Disposable rendered-camera acceptance server. Truth stays in evaluator files."""

from dataclasses import replace
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import cv2
import numpy as np
import uvicorn

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import utc_now
from teach_and_find.mobile.api import create_app
from teach_and_find.mobile.runtime import OperatorRuntime
from teach_and_find.planner import StationNode, TopologicalGraph
from teach_and_find.sim.world3d import (
    SimulatedLabWorld,
    PlacedObject,
    build_object_catalog,
    render_teaching_views,
)


def main():
    base = Path(os.environ["PUPPYPI_VISION_ACCEPTANCE_DIR"]).resolve()
    cfg = Settings()
    cfg = replace(
        cfg,
        vision=replace(cfg.vision, enabled=True),
        assistant=replace(cfg.assistant, data_dir=str(base / "state")),
        mobile=replace(
            cfg.mobile,
            pairing_token="synthetic-vision-acceptance",
            allow_physical_motion=False,
        ),
    )
    graph = TopologicalGraph()
    graph.add_node(StationNode("station", 1, (0.0, 2.25)))
    world = SimulatedLabWorld(graph, cfg.camera)
    catalog = build_object_catalog()
    keys = ["secret_box_1", "blue_tool_case", "emerald_med_kit"]
    for key in keys:
        # Explicit authored fixture preparation uses the historical OpenCV crop
        # selector. Only the resulting reference images enter learned inference.
        for i, (_, image) in enumerate(
            render_teaching_views(
                catalog[key], cfg.camera, angles_deg=(-60.0, 0.0, 60.0)
            )
        ):
            cv2.imwrite(str(base / f"reference-{key}-{i}.png"), image)
    manifest = {
        "mode": "synthetic",
        "input_source": "project_pinhole_renderer_not_physics",
        "reference_crop_method": "custom_opencv_foreground_fixture_preparation",
        "reference_keys": keys,
        "scenes": {},
    }
    # Novel conditions are specified after freezing the declared 0.80 / 0.05
    # development policy, before running the combined models on these images.
    scenes = [
        "moving",
        "empty",
        "decoy",
        "occluded",
        "changed_view",
        "novel_angle",
        "novel_lighting",
        "novel_distractors",
        "indistinguishable_front",
    ]
    manifest["evaluation_split"] = {
        s: "development" if i < 5 else "new_condition_after_policy_freeze"
        for i, s in enumerate(scenes)
    }
    for scene in scenes:
        truth = []
        for index in range(12):
            positions = [
                -0.26 + index * 0.005,
                0.02 + index * 0.005,
                0.29 + index * 0.005,
            ]
            placed = [
                PlacedObject(catalog[k], "station", (x, 2.0), -90.0)
                for k, x in zip(keys, positions)
            ]
            if scene == "empty":
                placed = []
            elif scene == "decoy":
                placed = [
                    PlacedObject(
                        catalog["lookalike_red_box"], "station", (0.0, 2.0), -90.0
                    )
                ]
            elif scene == "novel_distractors":
                placed = [
                    PlacedObject(
                        catalog["lookalike_red_box"], "station", (-0.18, 2.0), -120.0
                    ),
                    PlacedObject(
                        catalog["amber_sensor_cube"], "station", (0.18, 2.0), -105.0
                    ),
                ]
            elif scene == "indistinguishable_front":
                # Deliberately impossible exact-identity observation: a distinct
                # object has identical visible front/top; its different sides
                # are hidden. This truth is evaluator-only, never a model hint.
                textures = {
                    **catalog["lookalike_red_box"].face_textures,
                    "front": catalog["secret_box_1"].face_textures["front"],
                    "top": catalog["secret_box_1"].face_textures["top"],
                }
                alias = replace(catalog["lookalike_red_box"], face_textures=textures)
                placed = [PlacedObject(alias, "station", (0.0, 2.0), -90.0)]
            elif scene == "novel_angle":
                placed = [
                    replace(p, yaw_deg=a)
                    for p, a in zip(placed, [-105.0, -75.0, -120.0])
                ]
            yaw = 90.0 if scene != "changed_view" else 85.0
            lighting = 1.0 if scene != "changed_view" else 0.75
            camera_x, camera_y, pitch = 0.0, 1.15, -10.0
            if scene == "novel_angle":
                camera_x, yaw, pitch = 0.08, 100.0, -12.0
            if scene == "novel_lighting":
                camera_y, pitch, lighting = 1.05, -14.0, 0.55

            def render():
                return world.render_camera(
                    camera_x,
                    camera_y,
                    yaw,
                    pitch_rad=np.deg2rad(pitch),
                    noise_std=0,
                    lighting_scale=lighting,
                )

            world.place_station_objects([])
            background = render()
            visible_truth = []
            # Oracle masks are isolated renders, used only by the evaluator.
            for obj in placed:
                world.place_station_objects([obj])
                mask = np.any(render() != background, axis=2)
                ys, xs = np.where(mask)
                if len(xs) and scene != "occluded":
                    visible_truth.append(
                        {
                            "key": obj.spec.object_id,
                            "xyxy": [
                                int(xs.min()),
                                int(ys.min()),
                                int(xs.max() + 1),
                                int(ys.max() + 1),
                            ],
                        }
                    )
            world.place_station_objects(placed)
            image = (
                render()
                if scene != "occluded"
                else np.full((480, 640, 3), 128, np.uint8)
            )
            cv2.imwrite(str(base / f"{scene}-{index}.png"), image)
            truth.append(visible_truth)
        manifest["scenes"][scene] = truth
    (base / "truth.json").write_text(json.dumps(manifest, indent=2))
    (base / "scene.txt").write_text("moving")

    class RenderedCamera:
        mode = "synthetic"

        def __init__(self):
            self.scene = None
            self.session = None
            self.sequence = 0

        def read_frame(self):
            scene = (base / "scene.txt").read_text().strip()
            if scene != self.scene:
                self.scene, self.session, self.sequence = scene, str(uuid4()), 0
            self.sequence += 1
            index = (self.sequence - 1) % 12
            fid = f"{self.session}:{self.sequence}"
            image = cv2.imread(str(base / f"{scene}-{index}.png"))
            with (base / "capture-truth.jsonl").open("a") as stream:
                stream.write(
                    json.dumps({"frame_id": fid, "scene": scene, "index": index}) + "\n"
                )
            return CameraFrame(
                image,
                fid,
                utc_now(),
                time.monotonic(),
                0.0,
                True,
                {
                    "camera_id": "synthetic_vision_rgb",
                    "session_id": self.session,
                    "sequence": self.sequence,
                    "capture_time_basis": "host_rendered_replay_ingest_time",
                    "calibration_id": "synthetic_camera_settings",
                    "source": "pinhole_renderer_replay",
                },
            )

        def send_command(self, command):
            if command.vx_cm_s or command.yaw_rate_rad_s:
                raise RuntimeError("Acceptance camera does not execute movement.")

        def close(self):
            pass

    uvicorn.run(
        create_app(cfg, runtime=OperatorRuntime(cfg, RenderedCamera())),
        host="127.0.0.1",
        port=18768,
        access_log=False,
    )


if __name__ == "__main__":
    main()
