"""Closed-loop 3D visual episode runner and 4-way ablation benchmark."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from teach_and_find.apriltag_pose import AprilTagPoseEstimator
from teach_and_find.config import Settings
from teach_and_find.mission import (
    FailureAwareMissionController,
    MissionEvidenceReport,
    MissionState,
)
from teach_and_find.perception import (
    CandidateProposalGenerator,
    ObjectMemoryBank,
    SpatialAppearanceEncoder,
)
from teach_and_find.planner import (
    ActiveSearchPlanner,
    SequentialSearchPlanner,
    TopologicalGraph,
    build_default_lab_graph,
)
from teach_and_find.sim.world3d import (
    Object3DSpec,
    PlacedObject,
    SimulatedLabWorld,
    build_object_catalog,
    render_teaching_views,
)
from teach_and_find.verification import VerificationStatus


@dataclass
class EpisodeTrace:
    """Detailed outcome and visual snapshots from one closed-loop search episode."""

    variant_name: str
    true_target_station: str
    decoy_station: str
    report: MissionEvidenceReport
    ground_truth_success: bool
    false_verification: bool
    station_frames_annotated: dict[str, np.ndarray] = field(default_factory=dict)
    decoy_verify_crops: list[tuple[float, float, np.ndarray]] = field(default_factory=list)
    target_verify_crops: list[tuple[float, float, np.ndarray]] = field(default_factory=list)


@dataclass(frozen=True)
class AblationMetrics:
    """Aggregated experimental metrics across N randomized trials."""

    variant_name: str
    num_trials: int
    true_success_rate: float
    false_verification_rate: float
    avg_stations_checked: float
    avg_travel_distance_m: float
    avg_distractors_rejected: float
    tag_recovery_count: int


def _annotate_frame(
    frame: np.ndarray,
    station_id: str,
    tags_info: list[tuple[int, float, np.ndarray]],
    boxes_info: list[tuple[tuple[int, int, int, int], str, tuple[int, int, int]]],
) -> np.ndarray:
    vis = frame.copy()
    cv2.rectangle(vis, (0, 0), (vis.shape[1], 34), (24, 28, 34), -1)
    header = f"{station_id}"
    if tags_info:
        tid, dist_m, pts = tags_info[0]
        header += f" | AprilTag #{tid} pose: {dist_m:.2f}m"
        poly = pts.astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis, [poly], True, (0, 235, 255), 2)
    else:
        header += " | TAG LOST -> RECOVER_TAG"
    cv2.putText(vis, header, (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (240, 245, 250), 2)

    for (x, y, w, h), label, color in boxes_info:
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)
        cv2.rectangle(vis, (x, max(0, y - 22)), (min(vis.shape[1], x + max(w, 165)), y), color, -1)
        cv2.putText(vis, label, (x + 4, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1)
    return vis


def run_closed_loop_episode(
    variant_name: str,
    use_active_planner: bool,
    use_multi_view: bool,
    base_memory: ObjectMemoryBank,
    catalog: dict[str, Object3DSpec],
    true_target_station: str,
    decoy_station: str,
    other_station: str,
    lighting_scale: float = 1.0,
    noise_std: float = 2.5,
    inject_tag_dropout_station: str | None = None,
    capture_visuals: bool = False,
    seed: int = 0,
) -> EpisodeTrace:
    """Execute one complete closed-loop 3D visual search episode."""
    cfg = Settings()
    rng = np.random.default_rng(seed)
    graph: TopologicalGraph = build_default_lab_graph()
    world = SimulatedLabWorld(graph, cfg.camera, cfg.apriltag.station_tag_size_m)
    tag_estimator = AprilTagPoseEstimator(cfg.camera, cfg.apriltag)
    proposer = CandidateProposalGenerator(cfg.perception)

    # Clone memory so distractor caches within an episode don't leak across variants
    memory = copy.deepcopy(base_memory)

    # Place target, look-alike decoy, and distinct clutter object at the 3 stations
    placements: list[PlacedObject] = []
    station_object_map = {
        true_target_station: ("secret_box_1", True),
        decoy_station: ("lookalike_red_box", False),
        other_station: ("blue_tool_case", False),
    }
    object_poses_xy_outward: dict[str, tuple[float, float, float]] = {}
    for sid, (obj_key, is_targ) in station_object_map.items():
        sx, sy = graph.nodes[sid].position_xy
        outward = math.atan2(-sy, -sx)
        ox = sx + 0.28 * math.cos(outward)
        oy = sy + 0.28 * math.sin(outward)
        placements.append(
            PlacedObject(
                spec=catalog[obj_key],
                station_id=sid,
                center_xy_m=(ox, oy),
                yaw_deg=math.degrees(outward),
                is_target=is_targ,
            )
        )
        object_poses_xy_outward[sid] = (ox, oy, outward)
    world.place_station_objects(placements)

    planner = (
        ActiveSearchPlanner(graph, cfg.planner)
        if use_active_planner
        else SequentialSearchPlanner(graph)
    )
    controller = FailureAwareMissionController(
        graph=graph,
        memory=memory,
        planner=planner,
        settings=cfg,
        use_multi_view_verification=use_multi_view,
        return_home_on_success=True,
    )
    controller.start_mission("Secret Box #1", start_node_id="HOME")

    annotated_frames: dict[str, np.ndarray] = {}
    decoy_crops: list[tuple[float, float, np.ndarray]] = []
    target_crops: list[tuple[float, float, np.ndarray]] = []

    step_guard = 0
    while controller.state not in (MissionState.SUCCESS, MissionState.FAILED) and step_guard < 20:
        step_guard += 1
        choice = controller.choose_next_station()
        if choice is None:
            break
        sid = choice.station_id

        # Step 1: Visual servo & AprilTag alignment (with optional temporary tag dropout)
        if inject_tag_dropout_station == sid:
            rx0, ry0, ryaw0 = world.station_front_pose(sid, distance_m=0.92, lateral_offset_m=0.05)
            drop_frame = world.render_camera(
                rx0, ry0, ryaw0,
                pitch_rad=math.radians(-8.0),
                lighting_scale=lighting_scale,
                noise_std=noise_std,
                hide_apriltags=True,
                rng=rng,
            )
            controller.compute_tag_alignment_command(tag_estimator.detect(drop_frame))

        rx, ry, ryaw = world.station_front_pose(sid, distance_m=0.82)
        align_frame = world.render_camera(
            rx, ry, ryaw,
            pitch_rad=math.radians(-8.0),
            lighting_scale=lighting_scale,
            noise_std=noise_std,
            rng=rng,
        )
        tags = tag_estimator.detect(align_frame)
        aligned, _ = controller.compute_tag_alignment_command(tags)
        if not aligned:
            # Fine step to target standoff
            rx, ry, ryaw = world.station_front_pose(sid, distance_m=0.82)
            align_frame = world.render_camera(
                rx, ry, ryaw,
                pitch_rad=math.radians(-10.0),
                lighting_scale=lighting_scale,
                noise_std=noise_std,
                rng=rng,
            )
            tags = tag_estimator.detect(align_frame)
            controller.compute_tag_alignment_command(tags)

        # Step 2: Station overview scan for foreground object candidates (tag + floor visible)
        scan_frame = world.render_camera(
            rx, ry, ryaw,
            pitch_rad=math.radians(-7.5),
            lighting_scale=lighting_scale,
            noise_std=noise_std,
            rng=rng,
        )
        scan_tags = tag_estimator.detect(scan_frame)
        # Filter to local-station proposals (objects within ~1.1m project to >4,500 px on 640x480)
        proposals = [
            p for p in proposer.propose(scan_frame, tags=scan_tags) if p.area_px >= 4500
        ]

        vis_boxes: list[tuple[tuple[int, int, int, int], str, tuple[int, int, int]]] = []
        confirmed_here = False

        for idx, prop in enumerate(proposals):
            match0, _ = memory.match_crop(prop.crop_bgr, "Secret Box #1")
            if match0.best_proto_sim < cfg.perception.candidate_trigger_threshold:
                vis_boxes.append(
                    (prop.bbox_xywh, f"Ignore sim={match0.best_proto_sim:.2f}", (130, 130, 130))
                )
                continue

            if not use_multi_view:
                # Single-view ablation mode: approach to 0.45m head-on (0 deg) and threshold once
                ox, oy, outward = object_poses_xy_outward[sid]
                cx = ox + 0.45 * math.cos(outward)
                cy = oy + 0.45 * math.sin(outward)
                cyaw = math.degrees(math.atan2(oy - cy, ox - cx))
                close_frame = world.render_camera(
                    cx, cy, cyaw,
                    pitch_rad=math.radians(-16.0),
                    lighting_scale=lighting_scale,
                    noise_std=noise_std,
                    rng=rng,
                )
                close_props = proposer.propose(close_frame, tags=tag_estimator.detect(close_frame))
                eval_crop = close_props[0].crop_bgr if close_props else prop.crop_bgr
                m_single, _ = memory.match_crop(eval_crop, "Secret Box #1")
                if controller.evaluate_single_view_candidate(m_single, eval_crop):
                    confirmed_here = True
                    vis_boxes.append(
                        (prop.bbox_xywh, f"1-View CONFIRM {m_single.best_proto_sim:.2f}", (30, 185, 45))
                    )
                    break
                else:
                    vis_boxes.append(
                        (prop.bbox_xywh, f"1-View Reject {m_single.best_proto_sim:.2f}", (35, 60, 210))
                    )
            else:
                # Full Active View Verification (IEVE multi-angle arc around candidate)
                session = controller.start_candidate_verification(f"{sid}_cand_{idx}")
                ox, oy, outward = object_poses_xy_outward[sid]
                status = VerificationStatus.NEED_MORE_VIEWS

                while status == VerificationStatus.NEED_MORE_VIEWS:
                    ang = session.next_viewpoint_angle_deg()
                    if ang is None:
                        break
                    if session.history:
                        controller.compute_arc_viewpoint_command(
                            session.history[-1].view_angle_deg,
                            ang,
                            radius_m=0.45,
                        )
                        # Account for physical arc path around candidate
                        arc_step_m = 0.45 * abs(math.radians(ang - session.history[-1].view_angle_deg))
                        controller.total_travel_distance_m += arc_step_m

                    ray = outward + math.radians(ang)
                    cx = ox + 0.45 * math.cos(ray)
                    cy = oy + 0.45 * math.sin(ray)
                    cyaw = math.degrees(math.atan2(oy - cy, ox - cx))
                    v_frame = world.render_camera(
                        cx, cy, cyaw,
                        pitch_rad=math.radians(-16.0),
                        lighting_scale=lighting_scale,
                        noise_std=noise_std,
                        rng=rng,
                    )
                    v_props = [
                        p for p in proposer.propose(v_frame, tags=tag_estimator.detect(v_frame))
                        if p.area_px >= 8000
                    ]
                    if not v_props:
                        break
                    # Select the dominant close-range centered object being inspected
                    primary_prop = max(
                        v_props,
                        key=lambda p: p.area_px / (1.0 + abs(p.center_px[0] - 320.0) / 160.0),
                    )
                    status = controller.step_candidate_verification(primary_prop, ang, distance_m=0.45)
                    last_sim = session.history[-1].match.best_proto_sim
                    if capture_visuals:
                        if sid == decoy_station:
                            decoy_crops.append((ang, last_sim, primary_prop.crop_bgr.copy()))
                        elif sid == true_target_station:
                            target_crops.append((ang, last_sim, primary_prop.crop_bgr.copy()))

                if status == VerificationStatus.CONFIRMED:
                    confirmed_here = True
                    vis_boxes.append(
                        (prop.bbox_xywh, f"CONFIRMED P={controller.final_confidence:.2f}", (30, 185, 45))
                    )
                    break
                else:
                    vis_boxes.append(
                        (prop.bbox_xywh, "DECOY REJECTED (multi-view)", (25, 55, 220))
                    )

        if capture_visuals:
            t_meta = [(t.tag_id, t.distance_m, t.corners_px) for t in scan_tags]
            annotated_frames[sid] = _annotate_frame(scan_frame, sid, t_meta, vis_boxes)

        if not confirmed_here and controller.state != MissionState.SUCCESS:
            controller.finish_station_unsuccessful(coverage_factor=1.0)

    report = controller.build_report()
    gt_success = bool(report.succeeded and report.found_station_id == true_target_station)
    false_verif = bool(report.succeeded and report.found_station_id != true_target_station)

    return EpisodeTrace(
        variant_name=variant_name,
        true_target_station=true_target_station,
        decoy_station=decoy_station,
        report=report,
        ground_truth_success=gt_success,
        false_verification=false_verif,
        station_frames_annotated=annotated_frames,
        decoy_verify_crops=decoy_crops,
        target_verify_crops=target_crops,
    )


def run_ablation_suite(num_trials: int = 40, seed: int = 42) -> list[AblationMetrics]:
    """Run controlled 4-way ablation across randomized object placements & lighting."""
    cfg = Settings()
    rng = np.random.default_rng(seed)
    catalog = build_object_catalog()
    encoder = SpatialAppearanceEncoder(cfg.perception.crop_size)
    base_mem = ObjectMemoryBank(encoder, cfg.perception, cfg.planner)

    # Enroll target + 3 other known lab items (excluding the unseen Red Decoy Box!)
    taught_target = render_teaching_views(catalog["secret_box_1"], cfg.camera)
    base_mem.teach("Secret Box #1", [c for _, c in taught_target], [a for a, _ in taught_target])
    for other_key in ("blue_tool_case", "emerald_med_kit", "amber_sensor_cube"):
        tv = render_teaching_views(catalog[other_key], cfg.camera, angles_deg=(-60.0, 0.0, 60.0))
        base_mem.teach(catalog[other_key].display_name, [c for _, c in tv], [a for a, _ in tv])

    # Realistic semantic prior: target is stored most frequently at Station_C or Station_B
    station_ids = ["Station_A", "Station_B", "Station_C"]
    station_probs = [0.15, 0.30, 0.55]
    for _ in range(4):
        base_mem.record_sighting("Secret Box #1", "Station_C")
    for _ in range(2):
        base_mem.record_sighting("Secret Box #1", "Station_B")

    # Pre-sample identical trial scenarios for fair paired comparison across all 4 variants
    scenarios = []
    for t in range(num_trials):
        targ_st = str(rng.choice(station_ids, p=station_probs))
        rem = [s for s in station_ids if s != targ_st]
        rng.shuffle(rem)
        decoy_st, other_st = rem[0], rem[1]
        light = float(rng.uniform(0.84, 1.15))
        noise = float(rng.uniform(1.8, 5.5))
        dropout_st = str(rng.choice(station_ids)) if (t % 4 == 0) else None
        scenarios.append((targ_st, decoy_st, other_st, light, noise, dropout_st, 1000 + t))

    variants = [
        ("V0: Seq + 1-View (Baseline)", False, False),
        ("V1: ActivePlan + 1-View", True, False),
        ("V2: Seq + Multi-View", False, True),
        ("V3: Full Teach & Find", True, True),
    ]

    results: list[AblationMetrics] = []
    for v_name, use_active, use_mv in variants:
        traces = [
            run_closed_loop_episode(
                variant_name=v_name,
                use_active_planner=use_active,
                use_multi_view=use_mv,
                base_memory=base_mem,
                catalog=catalog,
                true_target_station=sc[0],
                decoy_station=sc[1],
                other_station=sc[2],
                lighting_scale=sc[3],
                noise_std=sc[4],
                inject_tag_dropout_station=sc[5],
                capture_visuals=False,
                seed=sc[6],
            )
            for sc in scenarios
        ]
        n = float(len(traces))
        results.append(
            AblationMetrics(
                variant_name=v_name,
                num_trials=len(traces),
                true_success_rate=100.0 * sum(t.ground_truth_success for t in traces) / n,
                false_verification_rate=100.0 * sum(t.false_verification for t in traces) / n,
                avg_stations_checked=sum(len(t.report.stations_visited) for t in traces) / n,
                avg_travel_distance_m=sum(t.report.total_travel_distance_m for t in traces) / n,
                avg_distractors_rejected=sum(t.report.rejected_distractors for t in traces) / n,
                tag_recovery_count=sum(t.report.tag_recovery_events for t in traces),
            )
        )
    return results
