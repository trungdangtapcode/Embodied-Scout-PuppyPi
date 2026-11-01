"""Authored Python/OpenCV storyboard; hardcoded poses/labels, no learned inference or RL."""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import cv2
import mujoco
import numpy as np
from PIL import Image

from teach_and_find.apriltag_pose import AprilTagPoseEstimator
from teach_and_find.sim.world3d import stamp_scripted_visual
from teach_and_find.config import Settings
from teach_and_find.perception import CandidateProposalGenerator
from teach_and_find.planner import ActiveSearchPlanner, build_default_lab_graph
from teach_and_find.sim.mujoco_arena import (
    build_mujoco_arena_xml,
    set_puppypi_pose_and_gait,
)
from teach_and_find.sim.world3d import SimulatedLabWorld


def _put_banner(
    img: np.ndarray, text: str, bg_bgr: tuple[int, int, int] = (24, 30, 38)
) -> np.ndarray:
    out = img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 36), bg_bgr, -1)
    cv2.putText(
        out,
        text,
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (245, 248, 252),
        2,
        cv2.LINE_AA,
    )
    return out


def _render_free_cam(
    renderer: mujoco.Renderer,
    data: mujoco.MjData,
    lookat: tuple[float, float, float],
    distance: float,
    azimuth_deg: float,
    elevation_deg: float,
) -> np.ndarray:
    cam = mujoco.MjvCamera()
    cam.lookat[:] = lookat
    cam.distance = distance
    cam.azimuth = azimuth_deg
    cam.elevation = elevation_deg
    renderer.update_scene(data, camera=cam)
    return cv2.cvtColor(renderer.render(), cv2.COLOR_RGB2BGR)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Authored storyboard only; no model/RL/navigation execution."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "runs" / "authored-storyboards" / "mujoco",
    )
    out_dir = parser.parse_args().output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = Settings()
    graph = build_default_lab_graph()
    geom_helper = SimulatedLabWorld(graph, cfg.camera, cfg.apriltag.station_tag_size_m)
    xml_path = build_mujoco_arena_xml(root, graph)

    model = mujoco.MjModel.from_xml_path(str(xml_path))
    data = mujoco.MjData(model)
    est = AprilTagPoseEstimator(cfg.camera, cfg.apriltag)
    proposer = CandidateProposalGenerator(cfg.perception)

    # Object centers for close multi-angle verification arcs
    obj_centers: dict[str, tuple[float, float, float]] = {}
    for sid in ("Station_A", "Station_B", "Station_C"):
        sx, sy = graph.nodes[sid].position_xy
        out = math.atan2(-sy, -sx)
        obj_centers[sid] = (sx + 0.28 * math.cos(out), sy + 0.28 * math.sin(out), out)

    # -------------------------------------------------------------------------
    # 1. Render 4-Panel High-Res 3D Showcase (`outputs/puppypi_3d_overview.png`)
    # -------------------------------------------------------------------------
    r_hi = mujoco.Renderer(model, height=480, width=720)

    # Panel A: Studio close-up of PuppyPi Standard at HOME
    set_puppypi_pose_and_gait(model, data, 0.0, 0.0, 90.0)
    p1 = _put_banner(
        _render_free_cam(r_hi, data, (0.0, 0.02, 0.085), 0.38, 52.0, -18.0),
        "1. Hiwonder PuppyPi Standard CAD (8-DOF + Head RGB Camera)",
    )

    # Panel B: Full 3D Arena Bird's-Eye Overview
    r_hi.update_scene(data, camera="arena_overview")
    p2 = _put_banner(
        cv2.cvtColor(r_hi.render(), cv2.COLOR_RGB2BGR),
        "2. 3D Topological Lab Arena (HOME + Stations A, B, C + AprilTags)",
    )

    # Panel C: PuppyPi arcing +58 deg around Red Decoy Box at Station C
    ox_c, oy_c, out_c = obj_centers["Station_C"]
    ray_c = out_c + math.radians(58.0)
    cx_c, cy_c = ox_c + 0.46 * math.cos(ray_c), oy_c + 0.46 * math.sin(ray_c)
    cyaw_c = math.degrees(math.atan2(oy_c - cy_c, ox_c - cx_c))
    set_puppypi_pose_and_gait(model, data, cx_c, cy_c, cyaw_c, trot_phase_rad=0.9)
    p3 = _put_banner(
        _render_free_cam(
            r_hi,
            data,
            (0.5 * (cx_c + ox_c), 0.5 * (cy_c + oy_c), 0.11),
            0.86,
            38.0,
            -24.0,
        ),
        "3. Station C: Active Side-View Arc Rejects Look-Alike Decoy",
        bg_bgr=(32, 42, 165),
    )

    # Panel D: PuppyPi confirming Secret Box #1 at Station A
    ox_a, oy_a, out_a = obj_centers["Station_A"]
    ray_a = out_a + math.radians(-55.0)
    cx_a, cy_a = ox_a + 0.46 * math.cos(ray_a), oy_a + 0.46 * math.sin(ray_a)
    cyaw_a = math.degrees(math.atan2(oy_a - cy_a, ox_a - cx_a))
    set_puppypi_pose_and_gait(model, data, cx_a, cy_a, cyaw_a, trot_phase_rad=0.0)
    p4 = _put_banner(
        _render_free_cam(
            r_hi,
            data,
            (0.5 * (cx_a + ox_a), 0.5 * (cy_a + oy_a), 0.11),
            0.86,
            cyaw_a + 145.0,
            -24.0,
        ),
        "4. Station A: Multi-View Confirmation of 'Secret Box #1'",
        bg_bgr=(32, 128, 48),
    )
    r_hi.close()

    grid_2x2 = np.vstack([np.hstack([p1, p2]), np.hstack([p3, p4])])
    overview_path = out_dir / "puppypi_3d_overview.png"
    cv2.imwrite(str(overview_path), stamp_scripted_visual(grid_2x2))

    # -------------------------------------------------------------------------
    # 2. Render Split-Screen 3D Animated Mission (`outputs/puppypi_3d_mission.gif`)
    # -------------------------------------------------------------------------
    r_main = mujoco.Renderer(model, height=540, width=720)
    r_sub = mujoco.Renderer(model, height=270, width=420)

    planner = ActiveSearchPlanner(graph, cfg.planner)
    belief = planner.initialize_belief()
    gif_frames: list[Image.Image] = []
    phase = 0.0

    def capture_composite(
        rx: float,
        ry: float,
        ryaw: float,
        walking: bool,
        chase_azim_offset: float,
        chase_dist: float,
        status_txt: str,
        status_col: tuple[int, int, int],
        fpv_badge: str = "",
        fpv_col: tuple[int, int, int] | None = None,
        hold: int = 1,
    ) -> None:
        nonlocal phase
        if walking:
            phase += 0.95
            set_puppypi_pose_and_gait(model, data, rx, ry, ryaw, trot_phase_rad=phase)
        else:
            set_puppypi_pose_and_gait(model, data, rx, ry, ryaw, trot_phase_rad=None)

        # Left: 3D Third-Person Chase Camera following PuppyPi
        look_x = rx + 0.22 * math.cos(math.radians(ryaw))
        look_y = ry + 0.22 * math.sin(math.radians(ryaw))
        chase_bgr = _render_free_cam(
            r_main,
            data,
            (look_x, look_y, 0.11),
            distance=chase_dist,
            azimuth_deg=ryaw + chase_azim_offset,
            elevation_deg=-23.0,
        )
        chase_bgr = _put_banner(
            chase_bgr, "3D MuJoCo Chase View — PuppyPi Standard (8-DOF)", (26, 32, 42)
        )
        cv2.rectangle(chase_bgr, (0, 504), (720, 540), status_col, -1)
        cv2.putText(
            chase_bgr,
            status_txt,
            (14, 528),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.54,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        # Top-Right: Onboard Head Camera (`head_rgb`) from PuppyPi's nose
        r_sub.update_scene(data, camera="head_rgb")
        fpv_bgr = cv2.cvtColor(r_sub.render(), cv2.COLOR_RGB2BGR)
        tags = est.detect(cv2.resize(fpv_bgr, (640, 480)))
        tag_lbl = (
            f" | Tag #{tags[0].tag_id} ({tags[0].distance_m:.2f}m)" if tags else ""
        )
        fpv_bgr = _put_banner(fpv_bgr, f"Head RGB Cam{tag_lbl}", (20, 24, 30))
        if fpv_badge and fpv_col is not None:
            cv2.rectangle(fpv_bgr, (10, 232), (410, 262), fpv_col, -1)
            cv2.putText(
                fpv_bgr,
                fpv_badge,
                (18, 252),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        # Bottom-Right: 3D Arena Bird's-Eye Camera + Live Bayesian Belief Overlay
        r_sub.update_scene(data, camera="arena_overview")
        bird_bgr = cv2.cvtColor(r_sub.render(), cv2.COLOR_RGB2BGR)
        bird_bgr = _put_banner(
            bird_bgr, "Arena Overview & Belief P(target|z)", (34, 42, 54)
        )
        # Draw compact belief bars
        cv2.rectangle(bird_bgr, (8, 224), (412, 264), (24, 28, 34), -1)
        for idx, sid in enumerate(("Station_A", "Station_B", "Station_C")):
            p_val = belief.get(sid, 0.0)
            x0 = 16 + idx * 132
            lbl = sid.replace("Station_", "")
            cv2.putText(
                bird_bgr,
                f"{lbl}:w={p_val:.2f}",
                (x0, 242),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.44,
                (240, 244, 248),
                1,
                cv2.LINE_AA,
            )
            cv2.rectangle(bird_bgr, (x0, 248), (x0 + 112, 258), (75, 82, 92), -1)
            cv2.rectangle(
                bird_bgr, (x0, 248), (x0 + int(112 * p_val), 258), (45, 185, 75), -1
            )

        right_col = np.vstack([fpv_bgr, bird_bgr])
        frame_rgb = cv2.cvtColor(
            stamp_scripted_visual(np.hstack([chase_bgr, right_col])), cv2.COLOR_BGR2RGB
        )
        pil_frame = Image.fromarray(frame_rgb)
        for _ in range(hold):
            gif_frames.append(pil_frame)

    def trot_path(
        p0: tuple[float, float, float],
        p1: tuple[float, float, float],
        steps: int,
        msg: str,
    ) -> None:
        walk_hdg = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        for s in range(1, steps + 1):
            a = s / float(steps)
            x = (1.0 - a) * p0[0] + a * p1[0]
            y = (1.0 - a) * p0[1] + a * p1[1]
            yaw = p1[2] if s == steps else walk_hdg
            capture_composite(x, y, yaw, True, -148.0, 0.95, msg, (58, 78, 108))

    # --- Execute 3D Mission Trajectory ---
    home = (0.0, 0.0, 90.0)
    capture_composite(
        *home,
        False,
        -140.0,
        0.85,
        "HOME: Taught 'Secret Box #1' (5 views) -> Starting Active Search",
        (45, 72, 112),
        hold=4,
    )

    # 1. Trot to Station C (Red Decoy Box)
    sc_pose = geom_helper.station_front_pose("Station_C", distance_m=0.72)
    trot_path(home, sc_pose, steps=6, msg="Trotting HOME -> Station C (scripted route)")
    capture_composite(
        *sc_pose,
        False,
        -145.0,
        0.82,
        "Station C [0 deg]: Red box matches frontally! Initiating side-view arc...",
        (30, 120, 200),
        "0 deg: authored comparison (Ambiguous -> Verify!)",
        (0, 145, 230),
        hold=4,
    )
    for arc in (20.0, 40.0, 60.0):
        ray = out_c + math.radians(arc)
        cx, cy = ox_c + 0.50 * math.cos(ray), oy_c + 0.50 * math.sin(ray)
        cyaw = math.degrees(math.atan2(oy_c - cy, ox_c - cx))
        done = abs(arc - 60.0) < 1e-3
        capture_composite(
            cx,
            cy,
            cyaw,
            not done,
            38.0 - cyaw,
            0.82,
            "Station C [+60 deg]: Hazard stripes on side! DECOY REJECTED!"
            if done
            else f"Lateral arc around candidate ({arc:+.0f} deg)...",
            (32, 42, 190) if done else (55, 85, 130),
            "REJECTED DECOY (side authored comparison)"
            if done
            else f"Arcing {arc:+.0f} deg (/velocity_move)",
            (32, 42, 205) if done else (0, 145, 230),
            hold=5 if done else 2,
        )
    belief = planner.register_negative_observation("Station_C", coverage_factor=1.0)

    # 2. Trot to Station B (Blue Tool Case clutter)
    sb_pose = geom_helper.station_front_pose("Station_B", distance_m=0.72)
    trot_path(
        (cx, cy, cyaw),
        sb_pose,
        steps=6,
        msg="Trotting Station C -> Station B (authored score)",
    )
    capture_composite(
        *sb_pose,
        False,
        -145.0,
        0.85,
        "Station B: Blue Tool Case ignored (authored comparison). authored station score!",
        (95, 75, 52),
        "Ignored clutter (authored comparison)",
        (110, 115, 122),
        hold=4,
    )
    belief = planner.register_negative_observation("Station_B", coverage_factor=1.0)

    # 3. Trot to Station A (True Target: Secret Box #1)
    sa_pose = geom_helper.station_front_pose("Station_A", distance_m=0.72)
    trot_path(
        sb_pose,
        sa_pose,
        steps=6,
        msg="Trotting Station B -> Station A (authored score)",
    )
    for arc in (0.0, -30.0, -58.0):
        ray = out_a + math.radians(arc)
        cx_a, cy_a = ox_a + 0.50 * math.cos(ray), oy_a + 0.50 * math.sin(ray)
        cyaw_a = math.degrees(math.atan2(oy_a - cy_a, ox_a - cx_a))
        conf = abs(arc + 58.0) < 1e-3
        if conf:
            belief = {"Station_A": 1.0, "Station_B": 0.0, "Station_C": 0.0}
        capture_composite(
            cx_a,
            cy_a,
            cyaw_a,
            not conf,
            142.0,
            0.82,
            "Station A [-58 deg]: Cyan cross-bars verified! TARGET CONFIRMED (authored label)!"
            if conf
            else f"Station A: Active multi-view check ({arc:+.0f} deg)...",
            (30, 142, 52) if conf else (42, 110, 75),
            "CONFIRMED 'Secret Box #1' (authored label)"
            if conf
            else f"View {arc:+.0f} deg: authored comparison",
            (30, 165, 55),
            hold=6 if conf else 2,
        )

    # 4. Return HOME
    trot_path(
        (cx_a, cy_a, cyaw_a),
        home,
        steps=6,
        msg="Target confirmed! Trotting back to HOME...",
    )
    capture_composite(
        *home,
        False,
        -140.0,
        0.85,
        "MISSION COMPLETE: Target reported + PuppyPi at authored HOME pose!",
        (28, 138, 50),
        "Returned HOME",
        (28, 150, 52),
        hold=6,
    )

    r_main.close()
    r_sub.close()

    gif_path = out_dir / "puppypi_3d_mission.gif"
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=220,
        loop=0,
        optimize=True,
    )
    # Remove temporary check image if present
    tmp = out_dir / "test_mujoco_check.png"
    if tmp.exists():
        tmp.unlink()

    print(f"Saved 4-panel 3D overview -> {overview_path}")
    print(
        f"Saved 3D animated MuJoCo simulation ({len(gif_frames)} frames) -> {gif_path}"
    )


if __name__ == "__main__":
    main()
