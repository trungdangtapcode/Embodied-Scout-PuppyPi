"""Smoke tests verifying core Teach & Find modules and Hiwonder ROS 2 driver guards."""

from __future__ import annotations

import math

from teach_and_find.apriltag_pose import AprilTagPoseEstimator
from teach_and_find.config import Settings
from teach_and_find.mission import FailureAwareMissionController, MissionState, PuppyActionCommand
from teach_and_find.perception import CandidateProposalGenerator, ObjectMemoryBank, SpatialAppearanceEncoder
from teach_and_find.planner import ActiveSearchPlanner, build_default_lab_graph
from teach_and_find.ros2_bridge import translate_action_to_ros_payload
from teach_and_find.sim.world3d import SimulatedLabWorld, build_object_catalog, render_teaching_views


def test_apriltag_6dof_pose_and_driver_quirks() -> None:
    cfg = Settings()
    graph = build_default_lab_graph()
    world = SimulatedLabWorld(graph, cfg.camera, cfg.apriltag.station_tag_size_m)
    rx, ry, ryaw = world.station_front_pose("Station_B", distance_m=0.82)
    frame = world.render_camera(rx, ry, ryaw, pitch_rad=math.radians(-6.0), noise_std=0.0)

    est = AprilTagPoseEstimator(cfg.camera, cfg.apriltag)
    tags = est.detect(frame)
    assert len(tags) == 1
    assert tags[0].tag_id == 2
    assert abs(tags[0].distance_m - 0.82) < 0.04

    # Verify lateral velocity routes to /puppy_control/velocity_move (Hiwonder puppy.py quirk)
    arc_cmd = PuppyActionCommand.clamped(cfg.motion, vy_cm_s=5.0, yaw_rate_rad_s=-0.1)
    payload = translate_action_to_ros_payload(arc_cmd, cfg)
    assert payload.velocity_topic == "/puppy_control/velocity_move"
    assert payload.pose_fields["yaw"] == 0.0


def test_planner_and_memory_lifecycle() -> None:
    cfg = Settings()
    graph = build_default_lab_graph()
    enc = SpatialAppearanceEncoder()
    mem = ObjectMemoryBank(enc, cfg.perception, cfg.planner)
    cat = build_object_catalog()

    taught = render_teaching_views(cat["secret_box_1"], cfg.camera)
    mem.teach("Secret Box #1", [c for _, c in taught], [a for a, _ in taught])
    mem.record_sighting("Secret Box #1", "Station_C")

    planner = ActiveSearchPlanner(graph, cfg.planner)
    ctrl = FailureAwareMissionController(graph, mem, planner, cfg)
    ctrl.start_mission("Secret Box #1")
    first = ctrl.choose_next_station()
    assert first is not None
    assert first.station_id == "Station_C"
    assert ctrl.state == MissionState.ALIGN_WITH_TAG
