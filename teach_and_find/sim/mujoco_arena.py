"""MuJoCo 3D scene builder using official Hiwonder PuppyPi Standard STL CAD meshes."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import mujoco
import numpy as np

from teach_and_find.apriltag_pose import AprilTagPoseEstimator
from teach_and_find.planner import TopologicalGraph, build_default_lab_graph
from teach_and_find.sim.world3d import PlacedObject, build_object_catalog


def _write_scene_textures(tex_dir: Path, graph: TopologicalGraph) -> dict[str, Path]:
    """Export PNG textures (flipped vertically for OpenGL UV origin) for MuJoCo 2D materials."""
    tex_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    est = AprilTagPoseEstimator()
    for _, node in graph.nodes.items():
        tag_bgr = est.generate_tag_image(node.apriltag_id, side_px=256, border_px=32)
        p = tex_dir / f"tag_{node.apriltag_id}.png"
        cv2.imwrite(str(p), tag_bgr)
        paths[f"tag_{node.apriltag_id}"] = p

    catalog = build_object_catalog()
    for obj_key, spec in catalog.items():
        for face_name in ("front", "right", "top"):
            p = tex_dir / f"{obj_key}_{face_name}.png"
            cv2.imwrite(str(p), spec.face_textures[face_name])
            paths[f"{obj_key}_{face_name}"] = p

    return paths


def build_mujoco_arena_xml(
    root_dir: Path,
    graph: TopologicalGraph | None = None,
    placements: list[PlacedObject] | None = None,
) -> Path:
    """Generate a self-contained MuJoCo MJCF XML combining PuppyPi CAD + 3D Lab Arena."""
    root_dir = root_dir.resolve()
    graph = graph or build_default_lab_graph()
    mesh_dir = root_dir / "assets" / "puppypi_description" / "meshes"
    gen_dir = root_dir / "assets" / "mujoco_generated"
    tex_dir = gen_dir / "textures"
    tex_paths = _write_scene_textures(tex_dir, graph)

    # Note on MuJoCo 2D box textures:
    # A thin plate `size="half_w half_h 0.001"` maps the 2D texture onto its local +Z face,
    # where local +X is horizontal width and local +Y is vertical height (`xyaxes="rx ry rz ux uy uz"`).
    station_bodies_xml: list[str] = []
    for sid, node in graph.nodes.items():
        sx, sy = node.position_xy
        if not node.is_search_station:
            # HOME pad on floor + low marker facing +Y (xyaxes="-1 0 0 0 0 1" -> +Z = (0,+1,0))
            station_bodies_xml.append(
                f"""
      <body name="station_{sid}" pos="{sx:.4f} {sy:.4f} 0.001">
        <geom type="cylinder" size="0.22 0.002" rgba="0.18 0.48 0.78 0.55" contype="0" conaffinity="0"/>
        <geom type="box" pos="0 -0.25 0.11" size="0.085 0.010 0.11" rgba="0.86 0.87 0.89 1" contype="0" conaffinity="0"/>
        <geom type="box" pos="0 -0.238 0.125" size="0.062 0.062 0.001" xyaxes="-1 0 0 0 0 1" material="mat_tag_{node.apriltag_id}" contype="0" conaffinity="0"/>
      </body>"""
            )
            continue

        outward = math.atan2(-sy, -sx)
        # Local +X points outward toward room center.
        # For front sign plate facing +X: right=(0,1,0), up=(0,0,1) -> +X_local x +Y_local = (1,0,0) = +X!
        station_bodies_xml.append(
            f"""
      <body name="station_{sid}" pos="{sx:.4f} {sy:.4f} 0" euler="0 0 {outward:.5f}">
        <geom type="cylinder" pos="0.28 0 0.0015" size="0.23 0.0015" rgba="0.28 0.35 0.44 0.38" contype="0" conaffinity="0"/>
        <geom type="box" pos="0 0 0.20" size="0.014 0.092 0.20" rgba="0.85 0.86 0.88 1" contype="0" conaffinity="0"/>
        <geom type="box" pos="0.016 0 0.27" size="0.068 0.068 0.001" xyaxes="0 1 0 0 0 1" material="mat_tag_{node.apriltag_id}" contype="0" conaffinity="0"/>
      </body>"""
        )

    object_bodies_xml: list[str] = []
    if placements is None:
        cat = build_object_catalog()
        default_map = {
            "Station_C": "lookalike_red_box",
            "Station_B": "blue_tool_case",
            "Station_A": "secret_box_1",
        }
        placements = []
        for sid, okey in default_map.items():
            sx, sy = graph.nodes[sid].position_xy
            out = math.atan2(-sy, -sx)
            placements.append(
                PlacedObject(
                    spec=cat[okey],
                    station_id=sid,
                    center_xy_m=(sx + 0.28 * math.cos(out), sy + 0.28 * math.sin(out)),
                    yaw_deg=math.degrees(out),
                )
            )

    for idx, pl in enumerate(placements):
        wx, wy, wz = pl.spec.size_xyz_m
        hx, hy, hz = 0.5 * wx, 0.5 * wy, 0.5 * wz
        ox, oy = pl.center_xy_m
        yaw_rad = math.radians(pl.yaw_deg)
        okey = pl.spec.object_id
        eps = 0.0015
        object_bodies_xml.append(
            f"""
      <body name="obj_{idx}_{okey}" pos="{ox:.4f} {oy:.4f} {hz:.4f}" euler="0 0 {yaw_rad:.5f}">
        <geom type="box" size="{hx:.4f} {hy:.4f} {hz:.4f}" rgba="0.18 0.18 0.20 1" contype="0" conaffinity="0"/>
        <!-- Front (+X): right=(0,1,0), up=(0,0,1) -> normal=(+1,0,0) -->
        <geom type="box" pos="{hx + eps:.4f} 0 0" size="{hy:.4f} {hz:.4f} 0.001" xyaxes="0 1 0 0 0 1" material="mat_{okey}_front" contype="0" conaffinity="0"/>
        <!-- Back (-X): right=(0,-1,0), up=(0,0,1) -> normal=(-1,0,0) -->
        <geom type="box" pos="{-hx - eps:.4f} 0 0" size="{hy:.4f} {hz:.4f} 0.001" xyaxes="0 -1 0 0 0 1" material="mat_{okey}_right" contype="0" conaffinity="0"/>
        <!-- Left side (+Y): right=(-1,0,0), up=(0,0,1) -> normal=(0,+1,0) -->
        <geom type="box" pos="0 {hy + eps:.4f} 0" size="{hx:.4f} {hz:.4f} 0.001" xyaxes="-1 0 0 0 0 1" material="mat_{okey}_right" contype="0" conaffinity="0"/>
        <!-- Right side (-Y): right=(1,0,0), up=(0,0,1) -> normal=(0,-1,0) -->
        <geom type="box" pos="0 {-hy - eps:.4f} 0" size="{hx:.4f} {hz:.4f} 0.001" xyaxes="1 0 0 0 0 1" material="mat_{okey}_right" contype="0" conaffinity="0"/>
        <!-- Top (+Z): normal=(0,0,+1) -->
        <geom type="box" pos="0 0 {hz + eps:.4f}" size="{hx:.4f} {hy:.4f} 0.001" material="mat_{okey}_top" contype="0" conaffinity="0"/>
      </body>"""
        )

    tex_asset_lines: list[str] = []
    mat_asset_lines: list[str] = []
    for key, p in sorted(tex_paths.items()):
        tex_asset_lines.append(f'    <texture name="tex_{key}" type="2d" file="{p.as_posix()}"/>')
        mat_asset_lines.append(
            f'    <material name="mat_{key}" texture="tex_{key}" texuniform="false" specular="0.06" shininess="0.1"/>'
        )

    xml_content = f"""<mujoco model="puppypi_teach_and_find">
  <compiler angle="radian" meshdir="{mesh_dir.as_posix()}"/>
  <visual>
    <headlight ambient="0.38 0.40 0.43" diffuse="0.28 0.28 0.30" specular="0.05 0.05 0.05"/>
    <rgba haze="0.88 0.91 0.95 1"/>
    <global offwidth="1280" offheight="960"/>
    <quality shadowsize="4096" offsamples="4"/>
  </visual>

  <asset>
    <texture name="skybox" type="skybox" builtin="gradient" rgb1="0.82 0.87 0.93" rgb2="0.95 0.96 0.98" width="512" height="512"/>
    <texture name="grid_tex" type="2d" builtin="checker" rgb1="0.73 0.76 0.80" rgb2="0.65 0.68 0.73" width="512" height="512" mark="edge" markrgb="0.57 0.60 0.65"/>
    <material name="floor_mat" texture="grid_tex" texrepeat="2 2" texuniform="true" specular="0.04" reflectance="0.03"/>

    <!-- Official Hiwonder PuppyPi Standard STL CAD Meshes -->
    <mesh name="base_link" file="base_link.STL"/>
    <mesh name="camera_link" file="camera_link.STL"/>
    <mesh name="lf_link1" file="lf_link1.STL"/>
    <mesh name="lf_link2" file="lf_link2.STL"/>
    <mesh name="rf_link1" file="rf_link1.STL"/>
    <mesh name="rf_link2" file="rf_link2.STL"/>
    <mesh name="lb_link1" file="lb_link1.STL"/>
    <mesh name="lb_link2" file="lb_link2.STL"/>
    <mesh name="rb_link1" file="rb_link1.STL"/>
    <mesh name="rb_link2" file="rb_link2.STL"/>

    <material name="puppy_chassis" rgba="0.16 0.18 0.22 1" specular="0.30" shininess="0.35"/>
    <material name="puppy_thigh" rgba="0.93 0.50 0.12 1" specular="0.40" shininess="0.45"/>
    <material name="puppy_shank" rgba="0.20 0.22 0.26 1" specular="0.30" shininess="0.35"/>
    <material name="puppy_cam" rgba="0.10 0.46 0.78 1" specular="0.45" shininess="0.5"/>
    <material name="puppy_foot" rgba="0.09 0.09 0.11 1" specular="0.08" shininess="0.1"/>

{chr(10).join(tex_asset_lines)}
{chr(10).join(mat_asset_lines)}
  </asset>

  <worldbody>
    <light name="sun_main" pos="0.2 -1.0 3.6" dir="-0.05 0.32 -0.94" diffuse="0.62 0.62 0.60" specular="0.08 0.08 0.08" castshadow="true"/>
    <light name="fill_left" pos="-2.0 1.8 2.6" dir="0.45 -0.25 -0.85" diffuse="0.28 0.30 0.34" specular="0.02 0.02 0.02" castshadow="false"/>

    <geom name="floor" type="plane" size="3.5 3.5 0.1" material="floor_mat"/>
    <geom name="wall_north" type="box" pos="0 2.75 0.22" size="2.35 0.04 0.22" rgba="0.84 0.86 0.89 1"/>
    <geom name="wall_west" type="box" pos="-2.15 1.10 0.22" size="0.04 1.70 0.22" rgba="0.82 0.84 0.87 1"/>
    <geom name="wall_east" type="box" pos="2.15 1.10 0.22" size="0.04 1.70 0.22" rgba="0.82 0.84 0.87 1"/>

    <camera name="arena_overview" pos="0.0 -1.55 1.95" xyaxes="1 0 0 0 0.56 0.83" fovy="52"/>
    <camera name="arena_corner" pos="-1.95 -1.10 1.42" xyaxes="0.54 -0.84 0 0.42 0.27 0.87" fovy="48"/>

{"".join(station_bodies_xml)}
{"".join(object_bodies_xml)}

    <!-- Hiwonder PuppyPi Standard 8-DOF Quadruped Robot -->
    <body name="puppy_base" pos="0 0 0.134">
      <joint name="root_x" type="slide" axis="1 0 0"/>
      <joint name="root_y" type="slide" axis="0 1 0"/>
      <joint name="root_z" type="slide" axis="0 0 1"/>
      <joint name="root_yaw" type="hinge" axis="0 0 1"/>
      <joint name="root_pitch" type="hinge" axis="0 1 0"/>
      <joint name="root_roll" type="hinge" axis="1 0 0"/>

      <!-- Third-person chase camera behind & slightly right of robot -->
      <camera name="chase_cam" pos="-0.62 -0.22 0.36" xyaxes="0.33 -0.94 0 0.38 0.13 0.92" fovy="54"/>

      <body name="base_dummy" pos="0 0 0" euler="0 0 1.5707963">
        <geom type="mesh" mesh="base_link" material="puppy_chassis" contype="0" conaffinity="0"/>

        <body name="camera_link" pos="0 -0.100687 0.017110" euler="0.034254 0 0">
          <geom type="mesh" mesh="camera_link" material="puppy_cam" contype="0" conaffinity="0"/>
          <!-- Looks forward along -Y of base_dummy (+X of puppy_base), pitched -10 deg down -->
          <camera name="head_rgb" pos="0 -0.026 0.010" xyaxes="-1 0 0 0 -0.1736 0.9848" fovy="54"/>
        </body>

        <body name="lf_link1" pos="0.042011 -0.077869 0.010651" euler="-0.752 0 0">
          <joint name="lf_joint1" type="hinge" axis="1 0 0" range="-2 2"/>
          <geom type="mesh" mesh="lf_link1" material="puppy_thigh" contype="0" conaffinity="0"/>
          <body name="lf_link2" pos="0.012050 0.052524 -0.052877">
            <joint name="lf_joint2" type="hinge" axis="1 0 0" range="-2 2"/>
            <geom type="mesh" mesh="lf_link2" material="puppy_shank" contype="0" conaffinity="0"/>
            <geom name="lf_foot" type="sphere" pos="0.003 -0.053 -0.053" size="0.010" material="puppy_foot" contype="0" conaffinity="0"/>
          </body>
        </body>

        <body name="rf_link1" pos="-0.042011 -0.077869 0.010651" euler="-0.752 0 0">
          <joint name="rf_joint1" type="hinge" axis="1 0 0" range="-2 2"/>
          <geom type="mesh" mesh="rf_link1" material="puppy_thigh" contype="0" conaffinity="0"/>
          <body name="rf_link2" pos="-0.018550 0.052524 -0.052877">
            <joint name="rf_joint2" type="hinge" axis="1 0 0" range="-2 2"/>
            <geom type="mesh" mesh="rf_link2" material="puppy_shank" contype="0" conaffinity="0"/>
            <geom name="rf_foot" type="sphere" pos="0.003 -0.053 -0.053" size="0.010" material="puppy_foot" contype="0" conaffinity="0"/>
          </body>
        </body>

        <body name="lb_link1" pos="0.042011 0.077869 0.015988" euler="-0.752 0 0">
          <joint name="lb_joint1" type="hinge" axis="1 0 0" range="-2 2"/>
          <geom type="mesh" mesh="lb_link1" material="puppy_thigh" contype="0" conaffinity="0"/>
          <body name="lb_link2" pos="0.012050 0.052524 -0.052877">
            <joint name="lb_joint2" type="hinge" axis="1 0 0" range="-2 2"/>
            <geom type="mesh" mesh="lb_link2" material="puppy_shank" contype="0" conaffinity="0"/>
            <geom name="lb_foot" type="sphere" pos="0.003 -0.053 -0.053" size="0.010" material="puppy_foot" contype="0" conaffinity="0"/>
          </body>
        </body>

        <body name="rb_link1" pos="-0.042011 0.077869 0.015988" euler="-0.752 0 0">
          <joint name="rb_joint1" type="hinge" axis="1 0 0" range="-2 2"/>
          <geom type="mesh" mesh="rb_link1" material="puppy_thigh" contype="0" conaffinity="0"/>
          <body name="rb_link2" pos="-0.018550 0.052524 -0.052877">
            <joint name="rb_joint2" type="hinge" axis="1 0 0" range="-2 2"/>
            <geom type="mesh" mesh="rb_link2" material="puppy_shank" contype="0" conaffinity="0"/>
            <geom name="rb_foot" type="sphere" pos="0.003 -0.053 -0.053" size="0.010" material="puppy_foot" contype="0" conaffinity="0"/>
          </body>
        </body>
      </body>
    </body>
  </worldbody>
</mujoco>
"""
    xml_path = gen_dir / "puppypi_arena.xml"
    xml_path.write_text(xml_content, encoding="utf-8")
    return xml_path


def set_puppypi_pose_and_gait(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    x: float,
    y: float,
    yaw_deg: float,
    pitch_deg: float = 0.0,
    trot_phase_rad: float | None = None,
) -> None:
    """Pose PuppyPi in natural standing stance or dynamic diagonal trot gait."""
    data.qpos[model.joint("root_x").qposadr[0]] = x
    data.qpos[model.joint("root_y").qposadr[0]] = y
    data.qpos[model.joint("root_yaw").qposadr[0]] = math.radians(yaw_deg)
    data.qpos[model.joint("root_pitch").qposadr[0]] = math.radians(pitch_deg)

    q1_stand = 0.36
    q2_stand = 0.74
    if trot_phase_rad is None:
        data.qpos[model.joint("root_z").qposadr[0]] = 0.0
        data.qpos[model.joint("root_roll").qposadr[0]] = 0.0
        for leg in ("lf", "rf", "lb", "rb"):
            data.qpos[model.joint(f"{leg}_joint1").qposadr[0]] = q1_stand
            data.qpos[model.joint(f"{leg}_joint2").qposadr[0]] = q2_stand
    else:
        # Subtle body bounce + diagonal leg pair trot (LF+RB vs RF+LB)
        data.qpos[model.joint("root_z").qposadr[0]] = 0.004 * abs(math.sin(trot_phase_rad))
        data.qpos[model.joint("root_roll").qposadr[0]] = 0.025 * math.sin(trot_phase_rad)
        for leg, phase_offset in (("lf", 0.0), ("rb", 0.0), ("rf", math.pi), ("lb", math.pi)):
            ph = trot_phase_rad + phase_offset
            swing = math.sin(ph)
            lift = max(0.0, math.cos(ph))
            data.qpos[model.joint(f"{leg}_joint1").qposadr[0]] = q1_stand + 0.26 * swing
            data.qpos[model.joint(f"{leg}_joint2").qposadr[0]] = q2_stand - 0.38 * lift

    mujoco.mj_forward(model, data)
