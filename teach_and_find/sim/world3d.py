"""Pinhole 640x480 3D renderer with real tag36h11 markers and multi-face textured objects."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from teach_and_find.apriltag_pose import AprilTagPoseEstimator
from teach_and_find.config import CameraSettings
from teach_and_find.planner import TopologicalGraph


@dataclass(frozen=True)
class Object3DSpec:
    """3D box dimensions and 4-face BGR texture maps (front, right, back, left, top)."""

    object_id: str
    display_name: str
    size_xyz_m: tuple[float, float, float]  # (width_x, depth_y, height_z)
    face_textures: dict[str, np.ndarray]  # keys: front, right, back, left, top


@dataclass(frozen=True)
class PlacedObject:
    """Object instance positioned on the floor/pedestal near a topological station."""

    spec: Object3DSpec
    station_id: str
    center_xy_m: tuple[float, float]
    yaw_deg: float  # Direction the object's 'front' face points
    base_z_m: float = 0.0
    is_target: bool = False


def _make_face_canvas(bg_bgr: tuple[int, int, int], size: int = 160) -> np.ndarray:
    canvas = np.full((size, size, 3), bg_bgr, dtype=np.uint8)
    # Subtle bevel border so edges are realistic
    cv2.rectangle(canvas, (3, 3), (size - 4, size - 4), (40, 40, 40), 2)
    return canvas


def _draw_emblem(
    canvas: np.ndarray,
    pattern: str,
    fg_bgr: tuple[int, int, int],
    accent_bgr: tuple[int, int, int],
) -> np.ndarray:
    img = canvas.copy()
    s = img.shape[0]
    c = s // 2
    if pattern == "gold_ring_star":
        cv2.circle(img, (c, c), int(0.32 * s), fg_bgr, 12)
        cv2.circle(img, (c, c), int(0.13 * s), accent_bgr, -1)
        cv2.line(img, (c - 34, c), (c + 34, c), fg_bgr, 5)
        cv2.line(img, (c, c - 34), (c, c + 34), fg_bgr, 5)
    elif pattern == "gold_ring_dot":
        # Deliberately almost identical to gold_ring_star from far frontal view!
        cv2.circle(img, (c, c), int(0.31 * s), fg_bgr, 12)
        cv2.circle(img, (c, c), int(0.14 * s), accent_bgr, -1)
    elif pattern == "cyan_cross_bars":
        cv2.rectangle(img, (18, c - 18), (s - 18, c + 18), fg_bgr, -1)
        cv2.rectangle(img, (c - 18, 18), (c + 18, s - 18), fg_bgr, -1)
        cv2.circle(img, (c, c), 16, accent_bgr, -1)
    elif pattern == "hazard_stripes":
        for offset in range(-s, s * 2, 34):
            pts = np.array(
                [[offset, s], [offset + 18, s], [offset + s + 18, 0], [offset + s, 0]],
                dtype=np.int32,
            )
            cv2.fillConvexPoly(img, pts, fg_bgr)
    elif pattern == "chevron":
        pts1 = np.array([[26, c + 20], [c, 32], [s - 26, c + 20]], dtype=np.int32)
        pts2 = np.array([[26, s - 24], [c, c - 8], [s - 26, s - 24]], dtype=np.int32)
        cv2.polylines(img, [pts1, pts2], False, fg_bgr, 14)
    elif pattern == "med_cross":
        cv2.circle(img, (c, c), int(0.36 * s), accent_bgr, -1)
        cv2.rectangle(img, (c - 12, c - 38), (c + 12, c + 38), fg_bgr, -1)
        cv2.rectangle(img, (c - 38, c - 12), (c + 38, c + 12), fg_bgr, -1)
    elif pattern == "checker":
        cell = s // 4
        for gy in range(4):
            for gx in range(4):
                if (gx + gy) % 2 == 0:
                    cv2.rectangle(
                        img,
                        (gx * cell + 6, gy * cell + 6),
                        ((gx + 1) * cell - 6, (gy + 1) * cell - 6),
                        fg_bgr,
                        -1,
                    )
    return img


def build_object_catalog() -> dict[str, Object3DSpec]:
    """Create 3D multi-face objects including a hard look-alike distractor pair.

    `secret_box_1` and `lookalike_red_box` share nearly identical crimson fronts
    with gold rings, differing strongly on their left/right side faces:
      - `secret_box_1` sides: bright cyan cross-bars on navy panel
      - `lookalike_red_box` sides: dark slate panel with yellow hazard stripes
    """
    crimson = (42, 38, 195)
    gold = (35, 205, 245)
    white = (242, 242, 242)

    secret_front = _draw_emblem(
        _make_face_canvas(crimson), "gold_ring_star", gold, white
    )
    secret_side = _draw_emblem(
        _make_face_canvas((130, 55, 25)), "cyan_cross_bars", (235, 225, 30), white
    )
    secret_top = _make_face_canvas((55, 50, 205))

    lookalike_front = _draw_emblem(
        _make_face_canvas(crimson), "gold_ring_dot", gold, white
    )
    lookalike_side = _draw_emblem(
        _make_face_canvas((52, 58, 62)), "hazard_stripes", (20, 210, 235), white
    )
    lookalike_top = _make_face_canvas((55, 50, 195))

    blue_front = _draw_emblem(_make_face_canvas((195, 95, 28)), "chevron", white, gold)
    blue_side = _draw_emblem(
        _make_face_canvas((165, 78, 22)), "chevron", (215, 225, 240), gold
    )

    green_front = _draw_emblem(
        _make_face_canvas((58, 155, 42)), "med_cross", white, (42, 115, 30)
    )
    green_side = _draw_emblem(
        _make_face_canvas((48, 138, 35)), "med_cross", white, (35, 98, 25)
    )

    amber_front = _draw_emblem(
        _make_face_canvas((25, 145, 235)), "checker", (32, 32, 38), white
    )
    amber_side = _draw_emblem(
        _make_face_canvas((22, 130, 215)), "checker", (32, 32, 38), white
    )

    return {
        "secret_box_1": Object3DSpec(
            object_id="secret_box_1",
            display_name="Secret Box #1",
            size_xyz_m=(0.13, 0.13, 0.14),
            face_textures={
                "front": secret_front,
                "right": secret_side,
                "left": secret_side,
                "back": secret_side,
                "top": secret_top,
            },
        ),
        "lookalike_red_box": Object3DSpec(
            object_id="lookalike_red_box",
            display_name="Red Decoy Box",
            size_xyz_m=(0.13, 0.13, 0.14),
            face_textures={
                "front": lookalike_front,
                "right": lookalike_side,
                "left": lookalike_side,
                "back": lookalike_side,
                "top": lookalike_top,
            },
        ),
        "blue_tool_case": Object3DSpec(
            object_id="blue_tool_case",
            display_name="Blue Tool Case",
            size_xyz_m=(0.14, 0.12, 0.13),
            face_textures={
                "front": blue_front,
                "right": blue_side,
                "left": blue_side,
                "back": blue_side,
                "top": _make_face_canvas((205, 105, 35)),
            },
        ),
        "emerald_med_kit": Object3DSpec(
            object_id="emerald_med_kit",
            display_name="Emerald Med Kit",
            size_xyz_m=(0.13, 0.13, 0.13),
            face_textures={
                "front": green_front,
                "right": green_side,
                "left": green_side,
                "back": green_side,
                "top": _make_face_canvas((65, 168, 48)),
            },
        ),
        "amber_sensor_cube": Object3DSpec(
            object_id="amber_sensor_cube",
            display_name="Amber Sensor Cube",
            size_xyz_m=(0.12, 0.12, 0.12),
            face_textures={
                "front": amber_front,
                "right": amber_side,
                "left": amber_side,
                "back": amber_side,
                "top": _make_face_canvas((30, 155, 240)),
            },
        ),
    }


@dataclass(frozen=True)
class _Quad3D:
    corners_world: np.ndarray  # shape (4, 3): TL, TR, BR, BL
    normal_world: np.ndarray  # shape (3,)
    texture_bgr: np.ndarray


class SimulatedLabWorld:
    """Renders 640x480 egocentric RGB views with real perspective AprilTags & 3D objects."""

    def __init__(
        self,
        graph: TopologicalGraph,
        camera: CameraSettings | None = None,
        tag_size_m: float = 0.10,
        tag_center_height_m: float = 0.27,
    ) -> None:
        self.graph = graph
        self.camera = camera or CameraSettings()
        self.tag_size_m = tag_size_m
        self.tag_center_height_m = tag_center_height_m
        self.tag_helper = AprilTagPoseEstimator(camera=self.camera)
        self.placed_objects: list[PlacedObject] = []

        self._station_tag_quads: dict[str, _Quad3D] = {}
        self._station_backboards: list[_Quad3D] = []
        self._build_station_markers()

    def _build_station_markers(self) -> None:
        """Mount a vertical backboard + 10cm tag36h11 marker at each topological station."""
        board_tex = np.full((120, 120, 3), (222, 220, 214), dtype=np.uint8)
        cv2.rectangle(board_tex, (2, 2), (117, 117), (160, 156, 150), 3)

        for sid, node in self.graph.nodes.items():
            if not node.is_search_station:
                continue
            sx, sy = node.position_xy
            # Station marker faces back toward the room origin (HOME at 0,0)
            outward_angle = math.atan2(-sy, -sx)
            normal = np.array(
                [math.cos(outward_angle), math.sin(outward_angle), 0.0],
                dtype=np.float64,
            )
            # Right axis when looking AT the marker from the front:
            # Cross(world_up, normal) points left of normal, so right-on-tag is cross(normal, world_up)
            # Wait: let's verify! If marker is at (0, 2.25), normal = (0, -1, 0).
            # Looking at marker from (0, 1.4) along +Y: camera right is +X = (1, 0, 0).
            # (-normal_y, normal_x, 0) = (1, 0, 0)! Exact match!
            tag_right = np.array([-normal[1], normal[0], 0.0], dtype=np.float64)
            tag_up = np.array([0.0, 0.0, 1.0], dtype=np.float64)

            # White quiet-zone border around generated marker is 32px around 256px (total 320px),
            # so physical quad width = tag_size_m * (320 / 256) = 1.25 * tag_size_m!
            tag_img = self.tag_helper.generate_tag_image(
                node.apriltag_id, side_px=256, border_px=32
            )
            quad_half = 0.5 * self.tag_size_m * (320.0 / 256.0)
            center = (
                np.array([sx, sy, self.tag_center_height_m], dtype=np.float64)
                + 0.003 * normal
            )

            tl = center - quad_half * tag_right + quad_half * tag_up
            tr = center + quad_half * tag_right + quad_half * tag_up
            br = center + quad_half * tag_right - quad_half * tag_up
            bl = center - quad_half * tag_right - quad_half * tag_up
            self._station_tag_quads[sid] = _Quad3D(
                corners_world=np.stack([tl, tr, br, bl], axis=0),
                normal_world=normal,
                texture_bgr=tag_img,
            )

            # Support stand / backboard behind the AprilTag
            b_half_w = 0.14
            b_center = np.array([sx, sy, 0.18], dtype=np.float64)
            btl = b_center - b_half_w * tag_right + 0.18 * tag_up
            btr = b_center + b_half_w * tag_right + 0.18 * tag_up
            bbr = b_center + b_half_w * tag_right - 0.18 * tag_up
            bbl = b_center - b_half_w * tag_right - 0.18 * tag_up
            self._station_backboards.append(
                _Quad3D(
                    corners_world=np.stack([btl, btr, bbr, bbl], axis=0),
                    normal_world=normal,
                    texture_bgr=board_tex,
                )
            )

    def station_front_pose(
        self,
        station_id: str,
        distance_m: float = 0.82,
        arc_angle_deg: float = 0.0,
        lateral_offset_m: float = 0.0,
    ) -> tuple[float, float, float]:
        """Compute robot (x, y, yaw_deg) viewing a station from distance_m and arc_angle_deg."""
        sx, sy = self.graph.nodes[station_id].position_xy
        base_outward = math.atan2(-sy, -sx)
        ray_angle = base_outward + math.radians(arc_angle_deg)
        rx = sx + distance_m * math.cos(ray_angle)
        ry = sy + distance_m * math.sin(ray_angle)
        # Camera looks back at station center (sx, sy)
        yaw_rad = math.atan2(sy - ry, sx - rx)
        # Optional slight lateral perturbation
        rx += lateral_offset_m * (-math.sin(yaw_rad))
        ry += lateral_offset_m * math.cos(yaw_rad)
        return rx, ry, math.degrees(yaw_rad)

    def place_station_objects(self, placements: list[PlacedObject]) -> None:
        self.placed_objects = list(placements)

    def _object_quads(self, placed: PlacedObject) -> list[_Quad3D]:
        wx, wy, wz = placed.spec.size_xyz_m
        hx, hy = 0.5 * wx, 0.5 * wy
        z0 = placed.base_z_m
        z1 = z0 + wz

        psi = math.radians(placed.yaw_deg)
        # Object 'front' normal points along (cos psi, sin psi, 0)
        fwd = np.array([math.cos(psi), math.sin(psi), 0.0], dtype=np.float64)
        # Looking AT the front face from outside, viewer's right is (-sin psi, cos psi, 0)
        v_right = np.array([-math.sin(psi), math.cos(psi), 0.0], dtype=np.float64)
        up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        c_xy = np.array(
            [placed.center_xy_m[0], placed.center_xy_m[1], 0.0], dtype=np.float64
        )

        # 8 vertices relative to base center
        p_fl_b = c_xy + hy * fwd - hx * v_right + z0 * up
        p_fr_b = c_xy + hy * fwd + hx * v_right + z0 * up
        p_br_b = c_xy - hy * fwd + hx * v_right + z0 * up
        p_bl_b = c_xy - hy * fwd - hx * v_right + z0 * up

        p_fl_t = p_fl_b + wz * up
        p_fr_t = p_fr_b + wz * up
        p_br_t = p_br_b + wz * up
        p_bl_t = p_bl_b + wz * up

        tex = placed.spec.face_textures
        return [
            # Front face (+fwd)
            _Quad3D(np.stack([p_fl_t, p_fr_t, p_fr_b, p_fl_b]), fwd, tex["front"]),
            # Viewer-right side face (+v_right)
            _Quad3D(np.stack([p_fr_t, p_br_t, p_br_b, p_fr_b]), v_right, tex["right"]),
            # Viewer-left side face (-v_right)
            _Quad3D(np.stack([p_bl_t, p_fl_t, p_fl_b, p_bl_b]), -v_right, tex["left"]),
            # Back face (-fwd)
            _Quad3D(np.stack([p_br_t, p_bl_t, p_bl_b, p_br_b]), -fwd, tex["back"]),
            # Top face (+up)
            _Quad3D(np.stack([p_bl_t, p_br_t, p_fr_t, p_fl_t]), up, tex["top"]),
        ]

    def render_camera(
        self,
        robot_x: float,
        robot_y: float,
        robot_yaw_deg: float,
        pitch_rad: float | None = None,
        camera_height_m: float | None = None,
        lighting_scale: float = 1.0,
        noise_std: float = 2.0,
        hide_apriltags: bool = False,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """Render a 640x480 BGR pinhole camera image from the robot's current pose."""
        w, h = self.camera.width, self.camera.height
        pitch = self.camera.default_pitch_rad if pitch_rad is None else pitch_rad
        cam_z = (
            self.camera.camera_height_m if camera_height_m is None else camera_height_m
        )

        psi = math.radians(robot_yaw_deg)
        # Camera basis in world coordinates
        f_axis = np.array(
            [
                math.cos(psi) * math.cos(pitch),
                math.sin(psi) * math.cos(pitch),
                math.sin(pitch),
            ],
            dtype=np.float64,
        )
        r_axis = np.array([math.sin(psi), -math.cos(psi), 0.0], dtype=np.float64)
        d_axis = np.cross(f_axis, r_axis)
        rot_cw = np.stack([r_axis, d_axis, f_axis], axis=0)  # shape (3, 3)
        cam_pos = np.array([robot_x, robot_y, cam_z], dtype=np.float64)

        # Render horizon-aligned wall and floor gradient background
        horizon_y = int(round(self.camera.cy + self.camera.fy * math.tan(pitch)))
        horizon_y = max(0, min(h, horizon_y))

        frame = np.zeros((h, w, 3), dtype=np.uint8)
        if horizon_y > 0:
            wall_col = np.clip(
                np.array([208, 212, 216]) * lighting_scale, 20, 250
            ).astype(np.uint8)
            frame[:horizon_y, :] = wall_col
        if horizon_y < h:
            ys = np.linspace(0.0, 1.0, h - horizon_y)[:, None, None]
            floor_far = np.array([172.0, 168.0, 162.0]) * lighting_scale
            floor_near = np.array([152.0, 148.0, 142.0]) * lighting_scale
            floor_grad = np.clip(
                (1.0 - ys) * floor_far + ys * floor_near, 15, 245
            ).astype(np.uint8)
            frame[horizon_y:, :] = np.broadcast_to(floor_grad, (h - horizon_y, w, 3))

        # Collect visible 3D quads
        all_quads: list[_Quad3D] = list(self._station_backboards)
        if not hide_apriltags:
            all_quads.extend(self._station_tag_quads.values())
        for obj in self.placed_objects:
            all_quads.extend(self._object_quads(obj))

        drawable: list[tuple[float, np.ndarray, np.ndarray, float]] = []
        light_dir = np.array([-0.25, -0.35, 0.90], dtype=np.float64)
        light_dir /= np.linalg.norm(light_dir)

        for quad in all_quads:
            quad_center = np.mean(quad.corners_world, axis=0)
            to_cam = cam_pos - quad_center
            # Back-face culling
            if float(np.dot(quad.normal_world, to_cam)) <= 0.0:
                continue

            pts_cam = (quad.corners_world - cam_pos[None, :]) @ rot_cw.T
            if np.any(pts_cam[:, 2] <= 0.06):
                continue

            us = self.camera.fx * (pts_cam[:, 0] / pts_cam[:, 2]) + self.camera.cx
            vs = self.camera.fy * (pts_cam[:, 1] / pts_cam[:, 2]) + self.camera.cy
            dst_pts = np.stack([us, vs], axis=1).astype(np.float32)

            # Skip quads completely outside image bounds
            if np.max(us) < 0 or np.min(us) >= w or np.max(vs) < 0 or np.min(vs) >= h:
                continue

            mean_depth = float(np.mean(pts_cam[:, 2]))
            shade = (
                0.76 + 0.24 * max(0.0, float(np.dot(quad.normal_world, light_dir)))
            ) * lighting_scale
            drawable.append((mean_depth, dst_pts, quad.texture_bgr, shade))

        # Painter's algorithm: farthest quad drawn first, closest drawn last
        drawable.sort(key=lambda item: item[0], reverse=True)
        for _, dst_pts, tex, shade in drawable:
            th, tw = tex.shape[:2]
            src_pts = np.array(
                [[0, 0], [tw - 1, 0], [tw - 1, th - 1], [0, th - 1]],
                dtype=np.float32,
            )
            shaded_tex = np.clip(tex.astype(np.float32) * shade, 0, 255).astype(
                np.uint8
            )
            homography = cv2.getPerspectiveTransform(src_pts, dst_pts)
            warped = cv2.warpPerspective(
                shaded_tex,
                homography,
                (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillConvexPoly(mask, np.round(dst_pts).astype(np.int32), 255)
            frame = np.where(mask[:, :, None] > 0, warped, frame)

        if noise_std > 0.0:
            gen = rng or np.random.default_rng(0)
            noise = gen.normal(0.0, noise_std, size=frame.shape).astype(np.float32)
            frame = np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)

        return frame


def render_teaching_views(
    spec: Object3DSpec,
    camera: CameraSettings | None = None,
    angles_deg: tuple[float, ...] = (-62.0, -30.0, 0.0, 30.0, 62.0),
    distance_m: float = 0.45,
    rng: np.random.Generator | None = None,
) -> list[tuple[float, np.ndarray]]:
    """Capture K=5 clean reference crops of an object from varied horizontal angles."""
    from teach_and_find.planner import StationNode, TopologicalGraph

    temp_graph = TopologicalGraph()
    temp_graph.add_node(
        StationNode(
            "TEACH_PEDESTAL",
            apriltag_id=9,
            position_xy=(0.0, 1.0),
            is_search_station=False,
        )
    )
    world = SimulatedLabWorld(temp_graph, camera=camera)
    world.place_station_objects(
        [
            PlacedObject(
                spec=spec,
                station_id="TEACH_PEDESTAL",
                center_xy_m=(0.0, 1.0),
                yaw_deg=-90.0,  # faces toward (0, 0)
                is_target=True,
            )
        ]
    )
    from teach_and_find.perception.proposals import CandidateProposalGenerator

    proposer = CandidateProposalGenerator()
    views: list[tuple[float, np.ndarray]] = []
    for ang in angles_deg:
        rad = math.radians(-90.0 + ang)
        rx = 0.0 + distance_m * math.cos(rad)
        ry = 1.0 + distance_m * math.sin(rad)
        yaw_deg = math.degrees(math.atan2(1.0 - ry, 0.0 - rx))
        frame = world.render_camera(
            rx,
            ry,
            yaw_deg,
            pitch_rad=math.radians(-16.0),
            lighting_scale=1.0,
            noise_std=1.5,
            hide_apriltags=True,
            rng=rng,
        )
        proposals = proposer.propose(frame)
        if proposals:
            crop = proposals[0].crop_bgr
        else:
            raise RuntimeError(
                f"No reference foreground at teaching angle {ang}; no substitute crop."
            )
        views.append((float(ang), crop))
    return views


def stamp_scripted_visual(image: np.ndarray) -> np.ndarray:
    """Label authored storyboard images; this is not model or motion evidence."""
    result = cv2.copyMakeBorder(
        image, 0, 48, 0, 0, cv2.BORDER_CONSTANT, value=(20, 24, 30)
    )
    for offset, text in (
        (18, "SCRIPTED | Python/OpenCV | no learned inference/RL"),
        (37, "Poses, labels and scores are hand-authored."),
    ):
        cv2.putText(
            result,
            text,
            (10, image.shape[0] + offset),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (245, 245, 245),
            1,
            cv2.LINE_AA,
        )
    return result
