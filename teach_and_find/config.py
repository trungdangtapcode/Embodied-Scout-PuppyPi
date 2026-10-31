"""Centralized operational defaults and hardware bounds for PuppyPi Standard."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CameraSettings:
    """Calibrated intrinsics matching Hiwonder src/peripherals/config/camera_info.yaml."""

    width: int = 640
    height: int = 480
    fx: float = 473.4506985
    fy: float = 474.2169451
    cx: float = 323.5512181
    cy: float = 238.6016133
    dist_coeffs: tuple[float, ...] = (
        -0.0274963,
        -0.0005352,
        -0.0058998,
        -0.0034231,
        -0.0355929,
    )
    camera_height_m: float = 0.145
    default_pitch_rad: float = math.radians(-10.0)


@dataclass(frozen=True)
class PuppyMotionLimits:
    """Conservative command bounds informed by vendor source; hardware unverified."""

    # VelocityFun requires |x| <= 35 cm/s and y == 0; VelocityMoveFun allows y != 0.
    max_vx_cm_s: float = 14.0
    max_vy_cm_s: float = 8.0
    max_yaw_rate_rad_s: float = math.radians(30.0)
    # PoseFun requires |roll| <= 31 deg, |pitch| <= 31 deg, yaw == 0, height in [-15, -5] cm.
    min_pitch_rad: float = math.radians(-28.0)
    max_pitch_rad: float = math.radians(15.0)
    stand_height_cm: float = -10.0
    stand_x_shift_cm: float = -0.5
    # Safe slow/stable trot gait for indoor inspection & approach
    gait_overlap_s: float = 0.20
    gait_swing_s: float = 0.18
    gait_clearance_s: float = 0.05
    gait_z_clearance_cm: float = 4.2


@dataclass(frozen=True)
class AprilTagSettings:
    """Station fiducial marker settings (tag36h11)."""

    family: str = "tag36h11"
    # Printed station tags should be 0.10m (10cm) instead of stock 0.033m tags
    # for reliable pose estimation up to 2.2m on a 640x480 camera.
    station_tag_size_m: float = 0.10
    stock_tag_size_m: float = 0.033
    standoff_distance_m: float = 0.82
    verify_distance_m: float = 0.46
    lost_tag_timeout_steps: int = 4


@dataclass(frozen=True)
class PerceptionSettings:
    """Encoder and few-shot object memory settings loaded from environment."""

    encoder_backend: str = field(
        default_factory=lambda: os.getenv("TEACH_FIND_ENCODER_BACKEND", "spatial_appearance")
    )
    torch_hub_repo: str = field(
        default_factory=lambda: os.getenv("TEACH_FIND_TORCH_HUB_REPO", "")
    )
    torch_hub_model: str = field(
        default_factory=lambda: os.getenv("TEACH_FIND_TORCH_HUB_MODEL", "")
    )
    device: str = field(
        default_factory=lambda: os.getenv("TEACH_FIND_DEVICE", "cpu")
    )
    crop_size: int = 96
    min_proposal_area_px: int = 550
    max_proposals_per_frame: int = 6
    # Single-view cosine similarity threshold for candidate triggering
    candidate_trigger_threshold: float = 0.60
    single_view_confirm_threshold: float = 0.74
    distractor_margin_weight: float = 0.35


@dataclass(frozen=True)
class VerificationSettings:
    """Active View Verification (IEVE-inspired sequential log-odds parameters)."""

    confirm_log_odds: float = 2.10   # ~89.1% posterior confidence
    reject_log_odds: float = -1.20   # ~23.1% posterior confidence
    max_verification_views: int = 4
    min_distinct_angles_for_confirm: int = 2
    min_angle_separation_deg: float = 22.0
    arc_angles_deg: tuple[float, ...] = (0.0, -60.0, 60.0, -38.0)
    similarity_midpoint: float = 0.72
    margin_midpoint: float = 0.08
    likelihood_temperature: float = 0.095


@dataclass(frozen=True)
class PlannerSettings:
    """Active Search Planner utility weights S(z) = alpha*P(z) - beta*D(z) + gamma*U(z)."""

    alpha_prior: float = 1.35
    beta_travel_cost: float = 0.45
    gamma_info_gain: float = 0.40
    # Detection probability when visiting a station that truly holds the target
    station_detection_recall: float = 0.90
    prior_dirichlet_smoothing: float = 0.35


@dataclass(frozen=True)
class Ros2TopicSettings:
    """ROS 2 Humble topics matching Hiwonder PuppyPi Standard."""

    image_topic: str = field(
        default_factory=lambda: os.getenv("PUPPYPI_IMAGE_TOPIC", "/image_raw")
    )
    velocity_topic: str = "/puppy_control/velocity"
    velocity_move_topic: str = "/puppy_control/velocity_move"
    pose_topic: str = "/puppy_control/pose"
    gait_topic: str = "/puppy_control/gait"
    imu_topic: str = "/ros_robot_controller/imu_raw"
    go_home_service: str = "/puppy_control/go_home"


@dataclass(frozen=True)
class EdgeRelaySettings:
    """Offboard Wi-Fi TCP relay defaults loaded from environment."""

    host: str = field(
        default_factory=lambda: os.getenv("PUPPYPI_RELAY_HOST", "127.0.0.1")
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("PUPPYPI_RELAY_PORT", "18765"))
    )
    jpeg_quality: int = 85
    socket_timeout_s: float = 2.0
    watchdog_timeout_s: float = 0.30


@dataclass(frozen=True)
class AssistantSettings:
    """Persistent operator workflows and uncalibrated evidence-quality gates."""

    data_dir: str = field(default_factory=lambda: os.getenv("TEACH_FIND_DATA_DIR", "data/assistant"))
    encoder_revision: str = field(default_factory=lambda: os.getenv("TEACH_FIND_ENCODER_REVISION", ""))
    minimum_quality: float = 0.60
    minimum_visibility: float = 0.80
    inspection_max_age_s: float = 300.0
    history_limit: int = 100
    demo_output_dir: str = "runs/assistant-demo"


@dataclass(frozen=True)
class MobileSettings:
    """Local operator console; hardware access must be explicitly selected."""

    host: str = "127.0.0.1"
    port: int = 8080
    robot_mode: str = "mock"
    allow_physical_motion: bool = False
    pairing_token: str = field(default_factory=lambda: os.getenv("PUPPYPI_OPERATOR_TOKEN", ""))
    session_lifetime_s: float = 28800.0
    command_lease_s: float = 0.45
    control_challenge_s: float = 0.45
    control_tick_s: float = 0.08
    frame_poll_s: float = 0.20
    transport_timeout_s: float = 0.25
    frame_buffer_size: int = 12
    max_frame_age_s: float = 1.0
    manual_speed_cm_s: float = 6.0
    manual_yaw_rate_rad_s: float = math.radians(20.0)
    max_upload_bytes: int = 4 * 1024 * 1024
    max_image_pixels: int = 8_000_000
    max_request_bytes: int = 6 * 1024 * 1024
    jpeg_quality: int = 80
    event_limit: int = 100


@dataclass(frozen=True)
class RoomSettings:
    """Bounded room-memory reads and optional scene-analysis output."""

    timeline_limit: int = 100
    query_evidence_limit: int = 5000
    recent_query_limit: int = 8
    matches_per_proposal: int = 3
    maximum_query_days: float = 365.0


@dataclass(frozen=True)
class Settings:
    """Top-level configuration bundle."""

    camera: CameraSettings = field(default_factory=CameraSettings)
    motion: PuppyMotionLimits = field(default_factory=PuppyMotionLimits)
    apriltag: AprilTagSettings = field(default_factory=AprilTagSettings)
    perception: PerceptionSettings = field(default_factory=PerceptionSettings)
    verification: VerificationSettings = field(default_factory=VerificationSettings)
    planner: PlannerSettings = field(default_factory=PlannerSettings)
    ros2: Ros2TopicSettings = field(default_factory=Ros2TopicSettings)
    edge_relay: EdgeRelaySettings = field(default_factory=EdgeRelaySettings)
    assistant: AssistantSettings = field(default_factory=AssistantSettings)
    mobile: MobileSettings = field(default_factory=MobileSettings)
    room: RoomSettings = field(default_factory=RoomSettings)
