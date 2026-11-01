"""ROS 2 Humble hardware bridge for Hiwonder PuppyPi Standard."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from teach_and_find.apriltag_pose import AprilTagPoseEstimator
from teach_and_find.config import Settings
from teach_and_find.mission import FailureAwareMissionController, PuppyActionCommand
from teach_and_find.perception.proposals import CandidateProposalGenerator


def teach_from_frame(
    memory, frame, name, proposer, tag_estimator, angle_deg=None
) -> bool:
    """Explicit foreground-first OpenCV teaching heuristic; no central-crop fallback.

    The operator supplies the name. This is not semantic identity recognition.
    Missing frames/proposals fail without mutating memory; unknown angles stay None.
    """
    if frame is None or frame.size == 0:
        return False
    tags = tag_estimator.detect(frame, undistort=True)
    proposals = proposer.propose(frame, tags=tags)
    if not proposals:
        return False
    existing = memory.get_record(name) if name in memory.object_names else None
    crops = list(existing.reference_crops) if existing else []
    angles = list(existing.view_angles_deg) if existing else []
    memory.teach(name, crops + [proposals[0].crop_bgr], angles + [angle_deg])
    return True


@dataclass(frozen=True)
class PublishedRosCommand:
    """Transport-agnostic record of serialized PuppyPi ROS 2 messages."""

    velocity_topic: str
    velocity_fields: dict[str, float]
    pose_topic: str
    pose_fields: dict[str, float | int]
    gait_topic: str | None = None
    gait_fields: dict[str, float] | None = None


def translate_action_to_ros_payload(
    cmd: PuppyActionCommand,
    settings: Settings,
    include_gait: bool = False,
) -> PublishedRosCommand:
    """Map a safe PuppyActionCommand onto exact puppy_control_msgs fields.

    Routes lateral motion (`vy_cm_s != 0`) to `/puppy_control/velocity_move`
    because `VelocityFun` in Hiwonder `puppy.py` drops commands when `y != 0`.
    Forces `yaw = 0.0` in `Pose` because `PoseFun` drops commands when `yaw != 0`.
    """
    vel_topic = (
        settings.ros2.velocity_move_topic
        if cmd.use_velocity_move_topic
        else settings.ros2.velocity_topic
    )
    vel_fields = {
        "x": float(cmd.vx_cm_s),
        "y": float(cmd.vy_cm_s),
        "yaw_rate": float(cmd.yaw_rate_rad_s),
    }
    pose_fields: dict[str, float | int] = {
        "roll": 0.0,
        "pitch": float(cmd.pitch_rad),
        "yaw": 0.0,
        "height": float(cmd.height_cm),
        "x_shift": float(settings.motion.stand_x_shift_cm),
        "stance_x": 0.0,
        "stance_y": 0.0,
        "run_time": 250,
    }
    gait_fields = None
    if include_gait:
        gait_fields = {
            "overlap_time": float(settings.motion.gait_overlap_s),
            "swing_time": float(settings.motion.gait_swing_s),
            "clearance_time": float(settings.motion.gait_clearance_s),
            "z_clearance": float(settings.motion.gait_z_clearance_cm),
        }
    return PublishedRosCommand(
        velocity_topic=vel_topic,
        velocity_fields=vel_fields,
        pose_topic=settings.ros2.pose_topic,
        pose_fields=pose_fields,
        gait_topic=settings.ros2.gait_topic if include_gait else None,
        gait_fields=gait_fields,
    )


def create_ros2_node(
    controller: FailureAwareMissionController,
    settings: Settings | None = None,
) -> Any:
    """Create a live `rclpy.node.Node` when deployed on PuppyPi / ROS 2 laptop.

    Imported lazily so offline simulation and unit tests run without ROS 2 installed.
    """
    import rclpy
    from cv_bridge import CvBridge
    from puppy_control_msgs.msg import Gait, Pose, Velocity
    from rclpy.node import Node
    from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import Image

    cfg = settings or Settings()

    class TeachAndFindRos2Node(Node):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__("puppypi_teach_and_find")
            self.cfg = cfg
            self.controller = controller
            self.bridge = CvBridge()
            self.tag_estimator = AprilTagPoseEstimator(cfg.camera, cfg.apriltag)
            self.proposer = CandidateProposalGenerator(cfg.perception)

            self._frame_lock = threading.Lock()
            self._latest_frame: np.ndarray | None = None

            sensor_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
            )
            self.image_sub = self.create_subscription(
                Image,
                cfg.ros2.image_topic,
                self._on_image,
                sensor_qos,
            )
            self.vel_pub = self.create_publisher(Velocity, cfg.ros2.velocity_topic, 10)
            self.vel_move_pub = self.create_publisher(
                Velocity, cfg.ros2.velocity_move_topic, 10
            )
            self.pose_pub = self.create_publisher(Pose, cfg.ros2.pose_topic, 10)
            self.gait_pub = self.create_publisher(Gait, cfg.ros2.gait_topic, 10)

            self._publish_action(
                PuppyActionCommand.clamped(cfg.motion), include_gait=True
            )
            self.timer = self.create_timer(0.15, self._control_tick)
            self.get_logger().info("PuppyPi Teach & Find ROS 2 node initialized.")

        def _on_image(self, msg: Any) -> None:
            # Non-blocking frame buffer (avoids blocking camera callback)
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            with self._frame_lock:
                self._latest_frame = np.asarray(frame, dtype=np.uint8)

        def get_latest_frame(self) -> np.ndarray | None:
            with self._frame_lock:
                return None if self._latest_frame is None else self._latest_frame.copy()

        def teach_from_live_view(
            self, name: str, angle_deg: float | None = None
        ) -> bool:
            admitted = teach_from_frame(
                self.controller.memory,
                self.get_latest_frame(),
                name,
                self.proposer,
                self.tag_estimator,
                angle_deg,
            )
            if not admitted:
                self.get_logger().error(
                    "TEACH_FAILED: no frame or foreground proposal; no substitute crop enrolled."
                )
            return admitted

        def _publish_action(
            self, cmd: PuppyActionCommand, include_gait: bool = False
        ) -> None:
            payload = translate_action_to_ros_payload(
                cmd, self.cfg, include_gait=include_gait
            )
            vel_msg = Velocity(**payload.velocity_fields)
            if cmd.use_velocity_move_topic:
                self.vel_move_pub.publish(vel_msg)
            else:
                self.vel_pub.publish(vel_msg)
            pose_msg = Pose(**payload.pose_fields)
            self.pose_pub.publish(pose_msg)
            if payload.gait_fields is not None:
                self.gait_pub.publish(Gait(**payload.gait_fields))

        def _control_tick(self) -> None:
            frame = self.get_latest_frame()
            if frame is None:
                return
            undistorted = cv2.undistort(
                frame,
                self.tag_estimator.camera_matrix,
                self.tag_estimator.dist_coeffs,
            )
            tags = self.tag_estimator.detect(undistorted, undistort=False)
            if self.controller.state.value == "SELECT_STATION":
                self.controller.choose_next_station()
            elif self.controller.state.value in ("ALIGN_WITH_TAG", "RECOVER_TAG"):
                _, cmd = self.controller.compute_tag_alignment_command(tags)
                self._publish_action(cmd)

    if not rclpy.ok():
        rclpy.init()
    return TeachAndFindRos2Node()
