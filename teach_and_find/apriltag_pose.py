"""Real 6-DoF AprilTag (tag36h11) detection and IPPE-Square pose estimation."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from teach_and_find.config import AprilTagSettings, CameraSettings


@dataclass(frozen=True)
class TagObservation:
    """Detected AprilTag 6-DoF observation in the robot camera frame.

    Camera coordinate convention (standard OpenCV pinhole):
      +X: right in image
      +Y: down in image
      +Z: forward optical axis (depth in meters)
    """

    tag_id: int
    corners_px: np.ndarray          # shape (4, 2), float32
    tvec_m: np.ndarray              # shape (3,), [x_right, y_down, z_forward] in meters
    rvec: np.ndarray                # shape (3,), Rodrigues rotation vector
    distance_m: float               # Euclidean distance ||tvec|| in meters
    bearing_rad: float              # Horizontal angle atan2(x_right, z_forward)
    viewing_yaw_rad: float          # Angle between camera optical axis and tag normal


class AprilTagPoseEstimator:
    """Detects tag36h11 markers and computes metric 6-DoF pose via IPPE-Square."""

    def __init__(
        self,
        camera: CameraSettings | None = None,
        tag_cfg: AprilTagSettings | None = None,
        tag_size_overrides: dict[int, float] | None = None,
    ) -> None:
        self.camera = camera or CameraSettings()
        self.tag_cfg = tag_cfg or AprilTagSettings()
        self.tag_size_overrides = dict(tag_size_overrides or {})

        self.camera_matrix = np.array(
            [
                [self.camera.fx, 0.0, self.camera.cx],
                [0.0, self.camera.fy, self.camera.cy],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        self.dist_coeffs = np.array(self.camera.dist_coeffs, dtype=np.float64)

        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.adaptiveThreshWinSizeMin = 5
        params.adaptiveThreshWinSizeMax = 35
        params.adaptiveThreshWinSizeStep = 6
        params.minMarkerPerimeterRate = 0.025
        self._dictionary = dictionary
        self._detector = cv2.aruco.ArucoDetector(dictionary, params)

    def generate_tag_image(self, tag_id: int, side_px: int = 256, border_px: int = 32) -> np.ndarray:
        """Render a crisp printable BGR AprilTag image with white quiet-zone border."""
        raw = cv2.aruco.generateImageMarker(self._dictionary, tag_id, side_px)
        padded = cv2.copyMakeBorder(
            raw,
            border_px,
            border_px,
            border_px,
            border_px,
            cv2.BORDER_CONSTANT,
            value=255,
        )
        return cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)

    def detect(self, bgr_frame: np.ndarray, undistort: bool = False) -> list[TagObservation]:
        """Detect all visible tag36h11 markers and estimate their metric 6-DoF poses."""
        if bgr_frame.ndim == 3:
            gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = bgr_frame

        corners_list, ids, _ = self._detector.detectMarkers(gray)
        if ids is None or len(ids) == 0:
            return []

        dist = self.dist_coeffs if undistort else np.zeros(5, dtype=np.float64)
        observations: list[TagObservation] = []

        for corners, raw_id in zip(corners_list, ids.flatten()):
            tag_id = int(raw_id)
            size_m = self.tag_size_overrides.get(tag_id, self.tag_cfg.station_tag_size_m)
            half = size_m / 2.0
            # IPPE_SQUARE object point ordering: top-left, top-right, bottom-right, bottom-left
            obj_pts = np.array(
                [
                    [-half, half, 0.0],
                    [half, half, 0.0],
                    [half, -half, 0.0],
                    [-half, -half, 0.0],
                ],
                dtype=np.float64,
            )
            img_pts = corners.reshape(4, 2).astype(np.float64)
            ok, rvec, tvec = cv2.solvePnP(
                obj_pts,
                img_pts,
                self.camera_matrix,
                dist,
                flags=cv2.SOLVEPNP_IPPE_SQUARE,
            )
            if not ok:
                continue

            t = tvec.reshape(3)
            if t[2] <= 0.02:
                continue

            rot_mat, _ = cv2.Rodrigues(rvec)
            # Tag normal in tag frame is +Z [0, 0, 1]; facing the camera means normal_cam.z < 0
            normal_cam = rot_mat[:, 2]
            viewing_yaw_rad = math.atan2(float(normal_cam[0]), float(-normal_cam[2]))
            distance_m = float(np.linalg.norm(t))
            bearing_rad = math.atan2(float(t[0]), float(t[2]))

            observations.append(
                TagObservation(
                    tag_id=tag_id,
                    corners_px=img_pts.astype(np.float32),
                    tvec_m=t.astype(np.float64),
                    rvec=rvec.reshape(3).astype(np.float64),
                    distance_m=distance_m,
                    bearing_rad=bearing_rad,
                    viewing_yaw_rad=viewing_yaw_rad,
                )
            )

        observations.sort(key=lambda obs: obs.distance_m)
        return observations
