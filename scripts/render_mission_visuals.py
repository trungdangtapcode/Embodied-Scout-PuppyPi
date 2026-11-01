"""Authored Python/OpenCV storyboard; hardcoded poses/labels, no learned inference or RL."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from teach_and_find.apriltag_pose import AprilTagPoseEstimator
from teach_and_find.sim.world3d import stamp_scripted_visual
from teach_and_find.config import Settings
from teach_and_find.perception import (
    CandidateProposalGenerator,
    ObjectMemoryBank,
    SpatialAppearanceEncoder,
)
from teach_and_find.planner import (
    ActiveSearchPlanner,
    TopologicalGraph,
    build_default_lab_graph,
)
from teach_and_find.sim.world3d import (
    PlacedObject,
    SimulatedLabWorld,
    build_object_catalog,
    render_teaching_views,
)


def _draw_topdown_panel(
    graph: TopologicalGraph,
    robot_xy: tuple[float, float],
    robot_yaw_deg: float,
    trail: list[tuple[float, float]],
    belief: dict[str, float],
    status_banner: str,
    banner_color: tuple[int, int, int],
    panel_w: int = 500,
    panel_h: int = 480,
) -> np.ndarray:
    """Render clean BGR top-down topological room map with PuppyPi pose, FOV cone, and beliefs."""
    canvas = np.full((panel_h, panel_w, 3), (246, 248, 250), dtype=np.uint8)

    # Coordinate transform: world x in [-2.0, 2.0], y in [-0.45, 2.75]
    def w2p(wx: float, wy: float) -> tuple[int, int]:
        px = int(round((wx + 2.0) / 4.0 * (panel_w - 60) + 30))
        py = int(round((1.0 - (wy + 0.45) / 3.20) * (panel_h - 95) + 55))
        return px, py

    # Grid lines
    for gx in np.linspace(-1.5, 1.5, 7):
        cv2.line(canvas, w2p(float(gx), -0.3), w2p(float(gx), 2.6), (230, 234, 238), 1)
    for gy in np.linspace(0.0, 2.5, 6):
        cv2.line(canvas, w2p(-1.8, float(gy)), w2p(1.8, float(gy)), (230, 234, 238), 1)

    # Topological edges
    drawn_edges: set[tuple[str, str]] = set()
    for u, nbrs in graph.adjacency.items():
        for v in nbrs:
            edge_key = (min(u, v), max(u, v))
            if edge_key in drawn_edges:
                continue
            drawn_edges.add(edge_key)
            p1 = w2p(*graph.nodes[u].position_xy)
            p2 = w2p(*graph.nodes[v].position_xy)
            cv2.line(canvas, p1, p2, (205, 212, 220), 2, cv2.LINE_AA)

    # Trajectory trail
    if len(trail) >= 2:
        pts = np.array([w2p(x, y) for x, y in trail], dtype=np.int32).reshape(
            (-1, 1, 2)
        )
        cv2.polylines(canvas, [pts], False, (235, 135, 45), 2, cv2.LINE_AA)

    # Station markers + live Bayesian belief bars
    station_tags = {
        "Station_A": ("Station A (Target)", (45, 155, 55)),
        "Station_B": ("Station B (Clutter)", (165, 95, 35)),
        "Station_C": ("Station C (Decoy!)", (45, 55, 205)),
        "HOME": ("HOME (Tag #0)", (90, 95, 105)),
    }
    for sid, node in graph.nodes.items():
        px, py = w2p(*node.position_xy)
        lbl, col = station_tags.get(sid, (sid, (80, 80, 80)))
        cv2.circle(canvas, (px, py), 13, col, -1, cv2.LINE_AA)
        cv2.circle(canvas, (px, py), 13, (30, 30, 35), 2, cv2.LINE_AA)
        cv2.putText(
            canvas,
            lbl,
            (max(8, px - 68), max(52, py - 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.44,
            (25, 30, 38),
            1,
            cv2.LINE_AA,
        )
        if sid in belief:
            prob = belief[sid]
            bx, by = max(10, px - 45), min(panel_h - 18, py + 20)
            cv2.rectangle(canvas, (bx, by), (bx + 90, by + 11), (218, 222, 228), -1)
            fill_w = int(round(90 * max(0.0, min(1.0, prob))))
            cv2.rectangle(canvas, (bx, by), (bx + fill_w, by + 11), (40, 165, 75), -1)
            cv2.rectangle(canvas, (bx, by), (bx + 90, by + 11), (120, 125, 135), 1)
            cv2.putText(
                canvas,
                f"weight={prob:.2f}",
                (bx + 22, by + 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (35, 40, 48),
                1,
                cv2.LINE_AA,
            )

    # Robot camera FOV wedge + quadruped body
    rx_p, ry_p = w2p(*robot_xy)
    fov_half = 31.0
    cone_len = 56
    a1 = math.radians(robot_yaw_deg - fov_half)
    a2 = math.radians(robot_yaw_deg + fov_half)
    c1 = (int(rx_p + cone_len * math.cos(a1)), int(ry_p - cone_len * math.sin(a1)))
    c2 = (int(rx_p + cone_len * math.cos(a2)), int(ry_p - cone_len * math.sin(a2)))
    overlay = canvas.copy()
    cv2.fillConvexPoly(
        overlay, np.array([[rx_p, ry_p], c1, c2], dtype=np.int32), (250, 210, 120)
    )
    canvas = cv2.addWeighted(overlay, 0.35, canvas, 0.65, 0)

    # PuppyPi body rectangle oriented along robot_yaw_deg
    yaw_r = math.radians(robot_yaw_deg)
    fwd = np.array([math.cos(yaw_r), -math.sin(yaw_r)])
    right = np.array([math.sin(yaw_r), math.cos(yaw_r)])
    center = np.array([rx_p, ry_p], dtype=np.float32)
    body_pts = np.array(
        [
            center + 14 * fwd - 9 * right,
            center + 14 * fwd + 9 * right,
            center - 14 * fwd + 9 * right,
            center - 14 * fwd - 9 * right,
        ],
        dtype=np.int32,
    )
    cv2.fillConvexPoly(canvas, body_pts, (35, 42, 52))
    nose = (int(rx_p + 18 * fwd[0]), int(ry_p + 18 * fwd[1]))
    cv2.circle(canvas, nose, 4, (0, 215, 255), -1, cv2.LINE_AA)

    # Top title & bottom status banner
    cv2.rectangle(canvas, (0, 0), (panel_w, 38), (30, 36, 46), -1)
    cv2.putText(
        canvas,
        "Top-Down Topological Map & Bayesian Belief",
        (14, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (245, 247, 250),
        2,
        cv2.LINE_AA,
    )
    cv2.rectangle(canvas, (0, panel_h - 36), (panel_w, panel_h), banner_color, -1)
    cv2.putText(
        canvas,
        status_banner,
        (12, panel_h - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return canvas


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Authored storyboard only; no model/RL/navigation execution."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=root / "runs" / "authored-storyboards" / "2d"
    )
    out_dir = parser.parse_args().output_dir.resolve()
    frames_dir = out_dir / "camera_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    cfg = Settings()
    graph = build_default_lab_graph()
    world = SimulatedLabWorld(graph, cfg.camera, cfg.apriltag.station_tag_size_m)
    catalog = build_object_catalog()
    est = AprilTagPoseEstimator(cfg.camera, cfg.apriltag)
    proposer = CandidateProposalGenerator(cfg.perception)
    encoder = SpatialAppearanceEncoder(cfg.perception.crop_size)
    memory = ObjectMemoryBank(encoder, cfg.perception, cfg.planner)

    # 1. Save taught 5-angle strip PNG
    taught = render_teaching_views(catalog["secret_box_1"], cfg.camera)
    memory.teach("Secret Box #1", [c for _, c in taught], [a for a, _ in taught])
    for k in ("blue_tool_case", "emerald_med_kit", "amber_sensor_cube"):
        tv = render_teaching_views(
            catalog[k], cfg.camera, angles_deg=(-60.0, 0.0, 60.0)
        )
        memory.teach(catalog[k].display_name, [c for _, c in tv], [a for a, _ in tv])

    strip_tiles = []
    for ang, crop in taught:
        tile = cv2.resize(crop, (160, 160))
        cv2.rectangle(tile, (0, 0), (160, 26), (25, 30, 38), -1)
        cv2.putText(
            tile,
            f"Teach {ang:+.0f} deg",
            (14, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (255, 255, 255),
            1,
        )
        strip_tiles.append(tile)
    cv2.imwrite(
        str(frames_dir / "00_taught_5_views.png"),
        stamp_scripted_visual(np.hstack(strip_tiles)),
    )

    # Place objects in the 3D world
    station_setup = {
        "Station_C": ("lookalike_red_box", False),
        "Station_B": ("blue_tool_case", False),
        "Station_A": ("secret_box_1", True),
    }
    placements: list[PlacedObject] = []
    obj_centers: dict[str, tuple[float, float, float]] = {}
    for sid, (okey, is_t) in station_setup.items():
        sx, sy = graph.nodes[sid].position_xy
        out = math.atan2(-sy, -sx)
        ox, oy = sx + 0.28 * math.cos(out), sy + 0.28 * math.sin(out)
        placements.append(
            PlacedObject(
                catalog[okey], sid, (ox, oy), math.degrees(out), is_target=is_t
            )
        )
        obj_centers[sid] = (ox, oy, out)
    world.place_station_objects(placements)

    planner = ActiveSearchPlanner(graph, cfg.planner)
    belief = planner.initialize_belief()

    gif_frames: list[Image.Image] = []
    trail: list[tuple[float, float]] = [(0.0, 0.0)]

    def record_step(
        rx: float,
        ry: float,
        ryaw: float,
        pitch_deg: float,
        cam_title: str,
        banner: str,
        banner_col: tuple[int, int, int],
        box_color: tuple[int, int, int] | None = None,
        box_label: str = "",
        save_png_name: str | None = None,
        hold_frames: int = 1,
    ) -> None:
        trail.append((rx, ry))
        cam = world.render_camera(
            rx, ry, ryaw, pitch_rad=math.radians(pitch_deg), noise_std=1.5
        )
        tags = est.detect(cam)
        props = [p for p in proposer.propose(cam, tags=tags) if p.area_px >= 4500]

        vis_cam = cam.copy()
        cv2.rectangle(vis_cam, (0, 0), (640, 38), (20, 24, 30), -1)
        tag_txt = (
            f" | Tag #{tags[0].tag_id} ({tags[0].distance_m:.2f}m)" if tags else ""
        )
        cv2.putText(
            vis_cam,
            f"PuppyPi 640x480 RGB: {cam_title}{tag_txt}",
            (12, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.54,
            (240, 245, 250),
            2,
            cv2.LINE_AA,
        )
        for t in tags:
            poly = t.corners_px.astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(vis_cam, [poly], True, (0, 230, 255), 2, cv2.LINE_AA)

        if props and box_color is not None:
            primary = max(
                props,
                key=lambda p: p.area_px / (1.0 + abs(p.center_px[0] - 320.0) / 160.0),
            )
            x, y, bw, bh = primary.bbox_xywh
            cv2.rectangle(vis_cam, (x, y), (x + bw, y + bh), box_color, 3)
            if box_label:
                cv2.rectangle(
                    vis_cam,
                    (x, max(38, y - 26)),
                    (min(638, x + max(bw, 220)), max(64, y)),
                    box_color,
                    -1,
                )
                cv2.putText(
                    vis_cam,
                    box_label,
                    (x + 6, max(56, y - 7)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.50,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

        if save_png_name:
            cv2.imwrite(str(frames_dir / save_png_name), stamp_scripted_visual(vis_cam))

        left = _draw_topdown_panel(
            graph, (rx, ry), ryaw, trail, belief, banner, banner_col
        )
        combined_bgr = stamp_scripted_visual(np.hstack([left, vis_cam]))
        pil_img = Image.fromarray(cv2.cvtColor(combined_bgr, cv2.COLOR_BGR2RGB))
        for _ in range(hold_frames):
            gif_frames.append(pil_img)

    def interpolate_walk(
        p0: tuple[float, float, float],
        p1: tuple[float, float, float],
        steps: int,
        label: str,
    ) -> None:
        for s in range(1, steps + 1):
            alpha = s / float(steps)
            x = (1.0 - alpha) * p0[0] + alpha * p1[0]
            y = (1.0 - alpha) * p0[1] + alpha * p1[1]
            walk_yaw = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
            yaw = p1[2] if s == steps else walk_yaw
            record_step(x, y, yaw, -8.0, label, f"Walking: {label}", (65, 85, 115))

    # --- Replay Sequence ---
    home_pose = (0.0, 0.0, 90.0)
    record_step(
        *home_pose,
        -8.0,
        "HOME Ready",
        "Mission Start: Find 'Secret Box #1'",
        (45, 70, 110),
        hold_frames=3,
    )

    # 1) Walk HOME -> Station_C (closest station under uniform prior)
    sc_front = world.station_front_pose("Station_C", distance_m=0.82)
    interpolate_walk(home_pose, sc_front, steps=4, label="HOME -> Station_C")
    record_step(
        *sc_front,
        -7.5,
        "Station_C Scan",
        "Station_C: Red box candidate spotted!",
        (35, 120, 195),
        (0, 165, 245),
        "Candidate authored comparison -> VERIFY",
        save_png_name="01_station_c_overview.png",
        hold_frames=3,
    )

    # Approach & arc around Red Decoy Box at Station_C
    ox, oy, out = obj_centers["Station_C"]
    c0 = (
        ox + 0.45 * math.cos(out),
        oy + 0.45 * math.sin(out),
        math.degrees(math.atan2(-math.sin(out), -math.cos(out))),
    )
    record_step(
        *c0,
        -16.0,
        "Verify @ 0 deg",
        "Station_C [0 deg]: Front looks identical (authored comparison) -> Arcing -60 deg!",
        (30, 125, 210),
        (0, 165, 245),
        "View 1 (0 deg): authored comparison (Need side view)",
        save_png_name="02_station_c_decoy_front.png",
        hold_frames=4,
    )
    for arc in (-30.0, -60.0):
        ray = out + math.radians(arc)
        cx, cy = ox + 0.45 * math.cos(ray), oy + 0.45 * math.sin(ray)
        cyaw = math.degrees(math.atan2(oy - cy, ox - cx))
        is_end = abs(arc + 60.0) < 1e-3
        record_step(
            cx,
            cy,
            cyaw,
            -16.0,
            f"Verify @ {arc:+.0f} deg",
            "DECOY REJECTED! Side has hazard stripes (sim dropped 0.98 -> 0.51)"
            if is_end
            else "Arcing laterally (/puppy_control/velocity_move)...",
            (35, 45, 195) if is_end else (65, 85, 115),
            (35, 45, 215) if is_end else (0, 165, 245),
            "REJECTED DECOY (side authored comparison)"
            if is_end
            else f"Arc {arc:+.0f} deg",
            save_png_name="03_station_c_decoy_rejected.png" if is_end else None,
            hold_frames=5 if is_end else 2,
        )

    belief = planner.register_negative_observation("Station_C", coverage_factor=1.0)

    # 2) Walk Station_C -> Station_B
    sb_front = world.station_front_pose("Station_B", distance_m=0.82)
    interpolate_walk((cx, cy, cyaw), sb_front, steps=4, label="Station_C -> Station_B")
    record_step(
        *sb_front,
        -7.5,
        "Station_B Scan",
        "Station_B: Blue Tool Case ignored (authored comparison). Belief shifts to A (83%)!",
        (95, 75, 55),
        (140, 140, 140),
        "Ignored clutter (authored comparison)",
        save_png_name="04_station_b_ignored.png",
        hold_frames=4,
    )
    belief = planner.register_negative_observation("Station_B", coverage_factor=1.0)

    # 3) Walk Station_B -> Station_A & confirm true Secret Box #1
    sa_front = world.station_front_pose("Station_A", distance_m=0.82)
    interpolate_walk(sb_front, sa_front, steps=4, label="Station_B -> Station_A")
    record_step(
        *sa_front,
        -7.5,
        "Station_A Scan",
        "Station_A (authored score): Candidate matched! Starting multi-view verify...",
        (35, 135, 65),
        (0, 185, 90),
        "Candidate authored comparison -> VERIFY",
        save_png_name="05_station_a_overview.png",
        hold_frames=3,
    )

    ox_a, oy_a, out_a = obj_centers["Station_A"]
    for arc in (0.0, -30.0, -60.0):
        ray = out_a + math.radians(arc)
        cx_a, cy_a = ox_a + 0.45 * math.cos(ray), oy_a + 0.45 * math.sin(ray)
        cyaw_a = math.degrees(math.atan2(oy_a - cy_a, ox_a - cx_a))
        is_conf = abs(arc + 60.0) < 1e-3
        if is_conf:
            belief = {"Station_A": 1.0, "Station_B": 0.0, "Station_C": 0.0}
        record_step(
            cx_a,
            cy_a,
            cyaw_a,
            -16.0,
            f"Verify @ {arc:+.0f} deg",
            "TARGET CONFIRMED! Cyan cross-bars verified on side (authored label)"
            if is_conf
            else "Verifying 'Secret Box #1' across angles...",
            (35, 150, 55) if is_conf else (45, 115, 85),
            (35, 185, 55),
            "CONFIRMED 'Secret Box #1' (authored label)"
            if is_conf
            else f"View ({arc:+.0f} deg): authored comparison",
            save_png_name="06_station_a_target_confirmed.png" if is_conf else None,
            hold_frames=6 if is_conf else 2,
        )

    # 4) Return HOME
    interpolate_walk((cx_a, cy_a, cyaw_a), home_pose, steps=4, label="Return -> HOME")
    record_step(
        *home_pose,
        -8.0,
        "HOME Mission Complete",
        "SCRIPTED story: found 'Secret Box #1' at Station_A & returned HOME!",
        (28, 138, 52),
        hold_frames=6,
    )

    gif_path = out_dir / "mission_replay.gif"
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=380,
        loop=0,
        optimize=True,
    )
    print(f"Saved animated replay ({len(gif_frames)} frames) -> {gif_path}")
    print(f"Saved disclosed camera PNGs (source frames plus scripted footer) -> {frames_dir}")


if __name__ == "__main__":
    main()
