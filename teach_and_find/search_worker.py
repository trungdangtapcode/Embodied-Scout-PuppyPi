"""Separate optional learned-search process; no physical actuation profile."""

import fcntl
import math
from pathlib import Path
import signal
import threading
import time

from teach_and_find.config import (
    CameraSettings,
    SearchSettings,
    Settings,
    VisionSettings,
)
from teach_and_find.errors import AssistantError
from teach_and_find.search_navigation import (
    KnownMapNavigator,
    VisualLocalizer,
    ROBOTICS_REVISION,
)
from teach_and_find.search_service import SearchService
from teach_and_find.search_verification import assess_views
from teach_and_find.storage import EvidenceStore
from teach_and_find.search_qualification import (
    profile_signature,
    identity_source_hashes,
)

STARTUP_SOURCE_HASHES = identity_source_hashes()


def execute_search(store, settings, job, stop_event=None):
    from teach_and_find.lightglue_adapter import LocalCorrespondence
    from teach_and_find.search_transport import SearchConnection
    from teach_and_find.yoloe_adapter import YoloeAdapter
    from teach_and_find.anomaly_adapter import AppearanceVerifier

    cfg = SearchSettings(**job["payload"]["search_profile"])
    vision = VisionSettings(**job["payload"]["vision_profile"])
    service = SearchService(store, settings)
    identifier = job["id"]
    connection = None
    appearance = None

    def check():
        if identity_source_hashes() != STARTUP_SOURCE_HASHES:
            raise AssistantError(
                "SEARCH_SOURCE_CHANGED",
                "Search implementation changed after worker startup; restart explicitly. No stale code execution claim.",
            )
        if stop_event is not None and stop_event.is_set():
            raise AssistantError(
                "SEARCH_WORKER_STOPPED",
                "Worker shutdown requested; no automatic resume.",
            )
        service.check(identifier)
        if connection:
            connection.check()

    try:
        if (
            job["payload"].get("schema_version") != 3
            or vision.profile_version != 3
            or cfg.profile_version != 3
        ):
            raise AssistantError(
                "SEARCH_PROFILE_UNSUPPORTED",
                "Only search v3 with required original anomaly inference / vision v3 may run; history is not upgraded.",
            )
        if job["mode"] != "synthetic" or not cfg.enabled or not vision.enabled:
            raise AssistantError(
                "SEARCH_PROFILE_UNSUPPORTED",
                "Required simulator/model profile disabled.",
            )
        calibration, references = (
            job["payload"]["calibration"],
            job["payload"]["references"],
        )
        target = next(r for r in references if r["object_id"] == job["object_id"])
        if (
            job["payload"].get("profile_signature")
            != profile_signature(settings, calibration, job["payload"])[0]
        ):
            raise AssistantError(
                "SEARCH_PROFILE_CHANGED",
                "Frozen search profile/source digest does not match this implementation; no historical reinterpretation.",
            )
        control_profile = job["payload"]["control_profile"]
        navigation = KnownMapNavigator(cfg, calibration)
        localizer = VisualLocalizer(
            calibration, CameraSettings(**job["payload"]["camera_profile"]), cfg
        )
        from teach_and_find.yoloe_adapter import verify_artifacts
        from teach_and_find.dinov2_adapter import verify_dinov2
        import torch

        verify_artifacts(vision)
        verify_dinov2(vision)
        torch.set_num_threads(vision.torch_threads)
        local = LocalCorrespondence(cfg)
        reference_features = [
            local.extract(store.load_image(sha)) for sha in target["image_shas"]
        ]
        appearance = AppearanceVerifier(store, cfg, vision, target["image_shas"], check)
        check()
        camera_identity = None
        views = []
        for station in calibration["stations"]:
            if len(views) >= cfg.max_inspection_views:
                break
            for goal in station["goals"]:
                if len(views) >= cfg.max_inspection_views:
                    break
                check()
                connection = SearchConnection(
                    cfg, identifier, calibration["id"], camera_identity
                )
                start_sample = connection.latest()
                pose = localizer.locate(start_sample["image"])
                route = navigation.plan(pose, goal)
                service.event(
                    identifier,
                    "route_planned",
                    {
                        "inspection_goal_region": station["id"],
                        "goal": goal,
                        "route": route,
                        "observed_start": pose,
                    },
                )
                deadline = time.monotonic() + cfg.navigation_timeout_s
                waypoint = 1
                last_frame = None
                position_reached = False
                while True:
                    check()
                    if time.monotonic() > deadline:
                        raise AssistantError(
                            "SEARCH_NAVIGATION_TIMEOUT",
                            "Observed goal convergence failed.",
                        )
                    sample = connection.latest()
                    if sample["frame_id"] == last_frame:
                        time.sleep(0.03)
                        continue
                    last_frame = sample["frame_id"]
                    pose = localizer.locate(sample["image"])
                    navigation.assert_clear(pose)
                    service.event(
                        identifier,
                        "pose_observed",
                        {
                            "frame_id": sample["frame_id"],
                            "captured_at": sample["captured_at"],
                            "pose": pose,
                        },
                    )
                    distance = math.dist([pose["x"], pose["y"]], goal[:2])
                    angle = math.atan2(
                        math.sin(goal[2] - pose["yaw"]), math.cos(goal[2] - pose["yaw"])
                    )
                    position_reached = (
                        position_reached or distance < cfg.goal_position_tolerance_m
                    )
                    if position_reached:
                        if distance > cfg.goal_drift_tolerance_m:
                            raise AssistantError(
                                "SEARCH_GOAL_DRIFT",
                                "Observed position moved outside the stationary goal envelope.",
                            )
                        if abs(angle) < math.radians(cfg.goal_yaw_tolerance_deg):
                            connection.stationary()
                            break
                        # Explicit terminal heading alignment; not a learned control claim.
                        connection.drive(0, angle / control_profile["yaw_rate_rad_s"])
                        continue
                    while (
                        waypoint < len(route) - 1
                        and math.dist([pose["x"], pose["y"]], route[waypoint]) < 0.18
                    ):
                        waypoint += 1
                    point = route[waypoint]
                    heading = (
                        goal[2]
                        if waypoint == len(route) - 1
                        else math.atan2(
                            route[min(waypoint + 1, len(route) - 1)][1] - point[1],
                            route[min(waypoint + 1, len(route) - 1)][0] - point[0],
                        )
                    )
                    _, v, w = navigation.command(pose, [*point, heading])
                    path_bearing = math.atan2(
                        point[1] - pose["y"], point[0] - pose["x"]
                    )
                    path_error = math.atan2(
                        math.sin(path_bearing - pose["yaw"]),
                        math.cos(path_bearing - pose["yaw"]),
                    )
                    # Explicit geometric rotation supervisor avoids the upstream
                    # forward/reverse switching boundary at +/-90 degrees.
                    if abs(path_error) > math.radians(60):
                        v, w = 0.0, path_error
                    connection.drive(
                        float(v) / control_profile["linear_speed_m_s"],
                        float(w) / control_profile["yaw_rate_rad_s"],
                    )
                # Wait for a capture after the zero command reached the independent loop.
                connection.disarm()
                time.sleep(cfg.settle_s)
                sample = connection.stationary_capture()
                camera_identity = connection.camera_identity
                connection.close()
                connection = None
                pose = localizer.locate(sample["image"])
                frame = {
                    k: sample[k] for k in ("frame_id", "captured_at", "provenance")
                }
                frame["image_sha"] = store.save_image(sample["image"])
                service.event(
                    identifier,
                    "inference_stationary",
                    {
                        "frame": frame,
                        "pose": pose,
                        "motion_disarmed_acknowledged": True,
                    },
                )
                inference_deadline = time.monotonic() + vision.job_timeout_s

                def inference_check():
                    check()
                    if time.monotonic() > inference_deadline:
                        raise AssistantError(
                            "SEARCH_INFERENCE_TIMEOUT",
                            "Required inference exceeded its configured budget.",
                        )

                adapter = YoloeAdapter(
                    vision,
                    lambda stage, record: service.event(identifier, stage, record),
                    inference_check,
                )
                inferred = adapter.run(
                    store, {"references": references, "frames": [frame]}
                )
                check()
                candidates = []
                for detection in inferred["frames"][0]["detections"]:
                    comparison = detection["reference_comparison"]
                    if comparison["best_object_id"] != target["object_id"]:
                        continue
                    x0, y0, x1, y1 = detection["xyxy"]
                    features = local.extract(
                        store.load_image(detection["crop_image_sha"])
                    )
                    matches = []
                    for index, ref in enumerate(reference_features):
                        check()
                        matches.append(
                            {
                                "reference_index": index,
                                "reference_sha": target["image_shas"][index],
                                **local.compare(ref, features),
                            }
                        )
                    candidates.append(
                        {
                            "object_id": target["object_id"],
                            "proposal_prompt_object_id": detection["prompt_object_id"],
                            "proposal_prompt_name": detection["prompt_name"],
                            "identity_name": comparison["best_name"],
                            "detection_index": detection["detection_index"],
                            "crop_image_sha": detection["crop_image_sha"],
                            "xyxy": detection["xyxy"],
                            "descriptor_supported": detection["reference_comparison"][
                                "decision"
                            ]
                            == "supported_candidate",
                            "reference_comparison": detection["reference_comparison"],
                            "floor_xy": localizer.floor_point(
                                [(x0 + x1) / 2, y1], pose
                            ),
                            "matches": matches,
                        }
                    )
                assessed = [c for c in candidates if c["descriptor_supported"]]
                for candidate, assessment in zip(assessed, appearance.assess(assessed)):
                    candidate["appearance"] = assessment
                record = {
                    "frame": frame,
                    "pose": pose,
                    "inspection_goal_region": station["id"],
                    "candidates": candidates,
                    "vision": inferred,
                    "local_model": {
                        **local.provenance,
                        "executed_calls": dict(local.calls),
                    },
                    "appearance_model": appearance.provenance,
                }
                service.view(identifier, record)
                views.append(record)
        result = assess_views(
            views, target["object_id"], len(target["image_shas"]), calibration, cfg
        )
        result["navigation_upstream_calls"] = navigation.calls
        result["navigation_provenance"] = {
            "repository": "https://github.com/AtsushiSakai/PythonRobotics",
            "revision": ROBOTICS_REVISION,
            "license": "MIT",
            "calibration_id": calibration["id"],
            "custom_supervisor": "declared_geometric_path_and_terminal_heading_alignment",
            "localization": "OpenCV AprilTag corners + PnP + constrained reprojection",
            "camera_profile": job["payload"]["camera_profile"],
            "distortion_used": "pinhole_zero_for_explicit_synthetic_profile",
        }
        result["local_model"] = {**local.provenance, "executed_calls": local.calls}
        result["evidence_mode"] = "synthetic_kinematic_rendered"
        service.event(identifier, "verification_evaluated", {"result": result})
        sighting = None
        if result["verdict"] == "confirmed":
            relevant = sorted({c["view"] for c in result["evidence"]})
            sighting = {
                "object_id": target["object_id"],
                "registered_name": target["name"],
                "method_profile": {"search": 3, "vision": 3, "geometry": 2},
                "station": result["station"],
                "captured_at": views[relevant[-1]]["frame"]["captured_at"],
                "source": "learned_models_with_custom_multiview_geometry",
                "mode": job["mode"],
                "search_id": identifier,
                "evidence_views": [
                    {"ordinal": i, "frame": views[i]["frame"]} for i in relevant
                ],
                "verdict": result,
                "current_state_established": False,
            }
        check()
        service.finish(identifier, result, sighting)
    except Exception as error:
        try:
            if "sample" in locals():
                service.event(
                    identifier,
                    "failure_capture",
                    {
                        "frame_id": sample["frame_id"],
                        "image_sha": store.save_image(sample["image"]),
                        "error": str(error),
                    },
                )
            service.finish(
                identifier,
                None,
                error={
                    "code": getattr(error, "code", "SEARCH_EXECUTION_FAILED"),
                    "type": type(error).__name__,
                    "message": str(error)[:1500],
                },
            )
        except AssistantError:
            pass  # A committed cancellation wins over late model/error output.
    finally:
        if connection:
            connection.close()
        if appearance:
            appearance.close()


def main():
    settings = Settings()
    if not settings.search.enabled:
        raise SystemExit("SEARCH_DISABLED")
    root = Path(settings.assistant.data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    with (root / "search-worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with EvidenceStore(root) as store:
            SearchService(store, settings).interrupt()

        def heartbeat():
            while not stopped.is_set():
                with EvidenceStore(root) as heartbeat_store:
                    SearchService(heartbeat_store, settings).seen()
                stopped.wait(1)

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            with EvidenceStore(root) as store:
                service = SearchService(store, settings)
                while not stopped.wait(0.2):
                    job = service.claim()
                    if job:
                        execute_search(store, settings, job, stopped)
        finally:
            stopped.set()
            thread.join(3)
            with EvidenceStore(root) as store:
                service = SearchService(store, settings)
                service.interrupt()
                service.seen("stopped")


if __name__ == "__main__":
    main()
