"""Declarative implementation inventory, not evidence that a model ran.

Keep this distinct from per-job provenance. Configuration and framework usage do
not establish paper-code reuse, pretrained inference, quality or hardware results.
"""

from teach_and_find.config import Settings


def implementation_summary(settings: Settings, mode: str) -> dict:
    cfg = settings.perception
    encoder = (
        {
            "name": "Object appearance encoder",
            "implementation": "project_owned_python_opencv_numpy_heuristic",
            "description": "Handcoded HSV/Lab/gradient features and fixed weights. No pretrained encoder or paper implementation runs in this baseline.",
            "source": "teach_and_find/perception/encoder.py:SpatialAppearanceEncoder",
            "research_repository": None,
        }
        if cfg.encoder_backend == "spatial_appearance"
        else {
            "name": "Object appearance encoder",
            "implementation": "optional_torch_hub_adapter"
            if cfg.encoder_backend == "torch_hub"
            else "unsupported_encoder",
            "description": "Configured optional encoder; configuration is not loading or inference evidence. Generic Torch Hub weights are not independently verified here.",
            "source": "teach_and_find/perception/encoder.py:build_encoder",
            "research_repository": None,
        }
    )
    components = [
        {
            "name": "Camera and motion preview",
            "implementation": "scripted_python_opencv_renderer"
            if mode == "synthetic"
            else "explicit_robot_adapter",
            "description": (
                "Predefined scene objects and poses, NumPy/OpenCV rendering and kinematic movement. No physics controller or RL policy."
                if mode == "synthetic"
                else "Camera frames and bounded command transport. Adapter acknowledgement does not measure robot motion."
            ),
            "source": "teach_and_find/mobile/devices.py",
            "research_repository": None,
        },
        encoder,
        {
            "name": "Foreground proposals and object matching",
            "implementation": "project_owned_python_opencv_heuristic",
            "description": "OpenCV color thresholds, morphology and contours; custom prototype similarity. Scores are uncalibrated. The operator confirms identity and region.",
            "source": "teach_and_find/scene.py; teach_and_find/perception/proposals.py",
            "research_repository": None,
        },
        {
            "name": "Recorded assertions and checklist assessment",
            "implementation": "project_owned_python_sqlite_rules",
            "description": "Python/SQLite rules over human or explicitly scripted assertions. No automatic visual inspection or learned room state.",
            "source": "teach_and_find/room.py; teach_and_find/inspection.py",
            "research_repository": None,
        },
        {
            "name": "Recorded-memory questions",
            "implementation": "optional_mind_palace_source_and_model_api",
            "description": "Pinned Mind Palace methods perform episodic/region/view retrieval and reasoning. Project adapters build records and validate contracts. Model execution is evidenced by individual job traces.",
            "source": "teach_and_find/mind_palace_adapter.py",
            "research_repository": "https://github.com/mind-palace-laeqa/benchmark",
            "configured_revision": settings.memory.upstream_revision,
            "configured_model": settings.memory.model,
            "enabled": settings.memory.enabled,
        },
        {
            "name": "Legacy station search and verification",
            "implementation": "custom_heuristics_on_declared_station_graph",
            "description": "Custom Dijkstra/station scores and fixed-angle verification. Synthetic evaluation uses oracle camera poses. No IEVE, VLFM, ViNT or NoMaD implementation is integrated.",
            "source": "teach_and_find/planner.py; teach_and_find/verification.py; teach_and_find/sim/evaluator.py",
            "research_repository": None,
        },
        {
            "name": "AprilTag pose estimation",
            "implementation": "opencv_aruco_detection_and_solvepnp_geometry",
            "description": "Actual OpenCV tag detection and geometric pose estimation. This is framework reuse, not a learned detector, navigation or obstacle avoidance.",
            "source": "teach_and_find/apriltag_pose.py",
            "research_repository": None,
        },
        {
            "name": "Visual prompting and video association",
            "implementation": "required_yoloe_dinov2_and_bytetrack_with_custom_reference_policy",
            "description": "Actual author YOLOE visual prompting and DINOv2 feature extraction, followed by a custom maximum-cosine/margin rule and upstream ByteTrack. The comparison rule is hand-selected and not calibrated; this is not an upstream exact-identity classifier. Both models are mandatory in the opt-in CPU worker. Per-job traces establish execution, not this configuration record.",
            "source": "teach_and_find/yoloe_adapter.py; teach_and_find/dinov2_adapter.py; teach_and_find/vision_worker.py",
            "research_repository": "https://github.com/THU-MIG/yoloe",
            "configured_revision": settings.vision.upstream_revision,
            "configured_model": settings.vision.model,
            "descriptor_repository": "https://github.com/facebookresearch/dinov2",
            "descriptor_revision": settings.vision.descriptor_revision,
            "descriptor_model": settings.vision.descriptor_model,
            "enabled": settings.vision.enabled,
        },
        {
            "name": "Calibrated station-search model worker",
            "implementation": "optional_yoloe_dinov2_bytetrack_disk_lightglue_custom_multiview_geometry",
            "description": "Separate CPU worker uses actual YOLOE/DINOv2/ByteTrack and pretrained DISK/LightGlue. Identity readout is custom geometric multi-view association, not IEVE or a calibrated probability. Known-map PythonRobotics A* and pose control consume AprilTag pixel localization. Authored map/goals and kinematic simulator are explicit inputs. Inspect run verdict/failures; this inventory does not certify quality.",
            "source": "teach_and_find/search_worker.py; teach_and_find/search_navigation.py; teach_and_find/lightglue_adapter.py",
            "research_repository": "https://github.com/cvg/LightGlue",
            "configured_revision": "5a650c444718caffc2669dc0094cde908f42dd73",
            "enabled": settings.search.enabled,
        },
        {
            "name": "Learned world model, VLA and RL",
            "implementation": "not_integrated",
            "description": "No learned predictive world model, vision-language-action policy or demonstrated RL locomotion. Visual-prompt detection and ByteTrack association do not establish these capabilities.",
            "source": "docs/00-project-status.md",
            "research_repository": None,
        },
    ]
    return {
        "schema_version": 1,
        "meaning": "declarative_configuration_and_code_inventory_not_per_run_execution_evidence",
        "mode": mode,
        "configured_encoder": cfg.encoder_backend,
        "components": components,
    }
