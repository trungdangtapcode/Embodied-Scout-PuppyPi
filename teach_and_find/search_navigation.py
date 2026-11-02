"""Known-map navigation using observed tag pixels and original PythonRobotics.

Map landmarks/goals are supplied calibration, never object detections or truth pose.
Optional SciPy and upstream code are imported only by the search worker.
"""

from __future__ import annotations

import importlib.util
import math
import sys

import cv2
import numpy as np

from teach_and_find.errors import AssistantError
from teach_and_find.model_artifacts import verified_checkout

ROBOTICS_REVISION = "8c392897c7f41a6e4d9aab9cb2e9737a7a6fa031"
LIGHTGLUE_REVISION = "5a650c444718caffc2669dc0094cde908f42dd73"


def pinned_source(path, revision):
    return verified_checkout(str(path), revision, "SEARCH")


def camera_rotation(yaw, pitch):
    forward = np.array(
        [
            math.cos(yaw) * math.cos(pitch),
            math.sin(yaw) * math.cos(pitch),
            math.sin(pitch),
        ]
    )
    right = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
    return np.stack([right, np.cross(forward, right), forward])


class VisualLocalizer:
    """AprilTag corners + calibrated, height/pitch-constrained reprojection fit.

    This is classical calibrated geometry, not learned localization or SLAM.
    """

    def __init__(self, calibration, camera, cfg):
        from scipy.optimize import least_squares

        self.optimize = least_squares  # Import before any motion lease is acquired.
        self.calibration, self.camera, self.cfg = calibration, camera, cfg
        self.k = np.array(
            [[camera.fx, 0, camera.cx], [0, camera.fy, camera.cy], [0, 0, 1.0]]
        )
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        parameters = cv2.aruco.DetectorParameters()
        parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        parameters.cornerRefinementWinSize = 3
        self.detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    def locate(self, image):
        detected, ids, _ = self.detector.detectMarkers(image)
        points, pixels, observed = [], [], []
        if ids is not None:
            for corners, identifier in zip(detected, ids.reshape(-1)):
                landmark = self.calibration["landmarks"].get(str(int(identifier)))
                if landmark is None:
                    continue
                points.extend(landmark["corners"])
                pixels.extend(corners.reshape(4, 2))
                observed.append(int(identifier))
        if len(points) < 4:
            raise AssistantError(
                "SEARCH_POSE_UNAVAILABLE",
                "No calibrated AprilTag observed; motion stopped.",
            )
        points, pixels = np.array(points, float), np.array(pixels, float)
        all_points, all_pixels = points, pixels
        ok, rv, tv, inliers = cv2.solvePnPRansac(
            points,
            pixels,
            self.k,
            np.zeros(5),
            iterationsCount=200,
            reprojectionError=self.cfg.pose_ransac_error_px,
            confidence=0.999,
            flags=cv2.SOLVEPNP_SQPNP,
        )
        if (
            not ok
            or inliers is None
            or len(inliers) < 4
            or len(inliers) / len(points) < self.cfg.pose_min_corner_inlier_fraction
        ):
            raise AssistantError("SEARCH_POSE_UNAVAILABLE", "PnP failed.")
        selected = inliers.reshape(-1)
        points, pixels = points[selected], pixels[selected]
        rotation = cv2.Rodrigues(rv)[0]
        center = -rotation.T @ tv
        forward = rotation.T[:, 2]
        initial = [
            float(center[0, 0]),
            float(center[1, 0]),
            math.atan2(forward[1], forward[0]),
        ]

        def residual(pose):
            r = camera_rotation(pose[2], self.camera.default_pitch_rad)
            c = np.array([pose[0], pose[1], self.camera.camera_height_m])
            xyz = (points - c) @ r.T
            uv = xyz @ self.k.T
            uv = uv[:, :2] / uv[:, 2:]
            return (uv - pixels).reshape(-1)

        fitted = self.optimize(residual, initial, max_nfev=100)
        rmse = float(np.sqrt(np.mean(fitted.fun**2)))
        x, y, yaw = map(float, fitted.x)
        final_rotation = camera_rotation(yaw, self.camera.default_pitch_rad)
        xyz_all = (
            all_points - np.array([x, y, self.camera.camera_height_m])
        ) @ final_rotation.T
        uv_all = xyz_all @ self.k.T
        error_all = np.linalg.norm(uv_all[:, :2] / uv_all[:, 2:] - all_pixels, axis=1)
        bounds = self.calibration["bounds"]
        if (
            not fitted.success
            or rmse > self.cfg.pose_max_reprojection_rmse_px
            or not bounds[0] < x < bounds[1]
            or not bounds[2] < y < bounds[3]
        ):
            raise AssistantError(
                "SEARCH_POSE_INVALID", f"Localization rejected (RMSE {rmse:.2f}px)."
            )
        return {
            "x": x,
            "y": y,
            "yaw": math.atan2(math.sin(yaw), math.cos(yaw)),
            "tag_ids": observed,
            "reprojection_rmse_px": rmse,
            "corner_inliers": len(selected),
            "corners_detected": len(all_points),
            "all_corner_errors_px": error_all.tolist(),
            "rejected_corner_indices": sorted(
                set(range(len(all_points))) - set(map(int, selected))
            ),
            "method": "opencv_apriltag_pnp_ransac_constrained_geometry",
        }

    def floor_point(self, pixel, pose):
        ray = np.linalg.inv(self.k) @ np.array([*pixel, 1.0])
        world = camera_rotation(pose["yaw"], self.camera.default_pitch_rad).T @ ray
        if world[2] >= -0.02:
            return None
        distance = -self.camera.camera_height_m / world[2]
        if not 0 < distance < 4:
            return None
        return (
            np.array([pose["x"], pose["y"], self.camera.camera_height_m])
            + distance * world
        )[:2].tolist()


class KnownMapNavigator:
    def __init__(self, cfg, calibration):
        root = pinned_source(cfg.robotics_source, ROBOTICS_REVISION)
        sys.path.insert(0, str(root))

        def load(name, relative):
            spec = importlib.util.spec_from_file_location(name, root / relative)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.show_animation = False
            return module

        self.astar = load("puppypi_upstream_astar", "PathPlanning/AStar/a_star.py")
        self.control = load(
            "puppypi_upstream_pose_control", "PathTracking/move_to_pose/move_to_pose.py"
        ).PathFinderController(cfg.position_gain, cfg.bearing_gain, cfg.heading_gain)
        self.calibration, self.cfg = calibration, cfg
        self.calls = {
            "AStarPlanner.planning": 0,
            "PathFinderController.calc_control_command": 0,
        }

    def plan(self, pose, goal):
        x0, x1, y0, y1 = self.calibration["bounds"]
        obstacles = [(x, y) for x in np.arange(x0, x1 + 0.05, 0.05) for y in (y0, y1)]
        obstacles += [(x, y) for y in np.arange(y0, y1 + 0.05, 0.05) for x in (x0, x1)]
        obstacles.extend(self.calibration.get("obstacles", []))
        ox, oy = zip(*obstacles)
        planner = self.astar.AStarPlanner(
            list(ox), list(oy), self.cfg.grid_resolution_m, self.cfg.footprint_radius_m
        )
        rx, ry = planner.planning(pose["x"], pose["y"], goal[0], goal[1])
        self.calls["AStarPlanner.planning"] += 1
        route = list(zip(rx, ry))[::-1]
        if (
            len(route) < 2
            or math.dist(route[0], [pose["x"], pose["y"]]) > 0.09
            or math.dist(route[-1], goal[:2]) > 0.09
        ):
            raise AssistantError(
                "SEARCH_NO_ROUTE", "Upstream planner did not return a complete route."
            )
        for x, y in route:
            self.assert_clear({"x": float(x), "y": float(y)})
        return [[float(x), float(y)] for x, y in route]

    def assert_clear(self, pose):
        x, y = pose["x"], pose["y"]
        x0, x1, y0, y1 = self.calibration["bounds"]
        radius = self.cfg.footprint_radius_m
        if not (x0 + radius < x < x1 - radius and y0 + radius < y < y1 - radius) or any(
            math.dist([x, y], obstacle) <= radius
            for obstacle in self.calibration.get("obstacles", [])
        ):
            raise AssistantError(
                "SEARCH_PATH_BLOCKED",
                "Observed/planned footprint intersects the supplied map; motion stopped.",
            )

    def command(self, pose, goal):
        self.calls["PathFinderController.calc_control_command"] += 1
        return self.control.calc_control_command(
            goal[0] - pose["x"], goal[1] - pose["y"], pose["yaw"], goal[2]
        )
