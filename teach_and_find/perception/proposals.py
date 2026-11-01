"""Project-owned Python/OpenCV saliency/contour heuristic with hand-tuned constants.

This does not load a learned detector or reuse a paper's perception implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from teach_and_find.apriltag_pose import TagObservation
from teach_and_find.config import PerceptionSettings


@dataclass(frozen=True)
class CandidateProposal:
    """Bounding box and crop of a candidate foreground object."""

    bbox_xywh: tuple[int, int, int, int]
    objectness: float
    center_px: tuple[float, float]
    area_px: int
    crop_bgr: np.ndarray


def _iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b
    ix1 = max(ax, bx)
    iy1 = max(ay, by)
    ix2 = min(ax + aw, bx + bw)
    iy2 = min(ay + ah, by + bh)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return float(inter) / float(max(union, 1))


class CandidateProposalGenerator:
    """Detects salient non-tag foreground objects without class-specific training."""

    def __init__(self, settings: PerceptionSettings | None = None) -> None:
        self.settings = settings or PerceptionSettings()

    def propose(
        self,
        bgr_frame: np.ndarray,
        tags: list[TagObservation] | None = None,
    ) -> list[CandidateProposal]:
        h, w = bgr_frame.shape[:2]
        lab = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2LAB).astype(np.float32)
        hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV).astype(np.float32)

        # Estimate background wall & floor chromaticity from border strips
        wall_strip = lab[int(0.05 * h) : int(0.25 * h), :, :]
        floor_strip = lab[int(0.84 * h) : int(0.98 * h), :, :]
        wall_med = np.median(wall_strip.reshape(-1, 3), axis=0)
        floor_med = np.median(floor_strip.reshape(-1, 3), axis=0)

        # Emphasize opponent-chrominance (a, b) over raw luminance (L) so achromatic
        # black/white fiducial borders or shadows never merge into foreground object crops.
        weights_lab = np.array([0.22, 1.15, 1.15], dtype=np.float32)
        dist_wall = np.linalg.norm(
            (lab - wall_med[None, None, :]) * weights_lab, axis=2
        )
        dist_floor = np.linalg.norm(
            (lab - floor_med[None, None, :]) * weights_lab, axis=2
        )
        color_saliency = np.minimum(dist_wall, dist_floor)

        # Combine chromatic salience and HSV saturation
        sat = hsv[:, :, 1]
        score_map = 0.65 * color_saliency + 0.35 * sat
        # Mask upper ceiling region where floor/pedestal objects cannot sit
        score_map[: int(0.16 * h), :] = 0.0

        # Mask out detected AprilTags (including white quiet zone) so tags aren't proposed
        if tags:
            for tag in tags:
                pts = tag.corners_px.astype(np.int32)
                x, y, tw, th = cv2.boundingRect(pts)
                pad_x = max(10, int(0.28 * tw))
                pad_y = max(10, int(0.28 * th))
                x1 = max(0, x - pad_x)
                y1 = max(0, y - pad_y)
                x2 = min(w, x + tw + pad_x)
                y2 = min(h, y + th + pad_y)
                score_map[y1:y2, x1:x2] = 0.0

        # Adaptive foreground threshold
        positive_vals = score_map[score_map > 1.0]
        if positive_vals.size == 0:
            return []
        thresh = max(24.0, float(np.percentile(positive_vals, 78)))
        mask = (score_map >= thresh).astype(np.uint8) * 255

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        raw_boxes: list[tuple[tuple[int, int, int, int], float]] = []

        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            if area < self.settings.min_proposal_area_px:
                continue
            if bw > int(0.82 * w) or bh > int(0.82 * h):
                continue
            aspect = float(bw) / float(max(bh, 1))
            if aspect < 0.25 or aspect > 3.6:
                continue

            roi_scores = score_map[y : y + bh, x : x + bw]
            fill_ratio = float(cv2.contourArea(cnt)) / float(max(area, 1))
            objectness = float(np.mean(roi_scores) / 90.0) * (0.5 + 0.5 * fill_ratio)
            raw_boxes.append(((x, y, bw, bh), min(1.0, objectness)))

        # Non-Maximum Suppression
        raw_boxes.sort(key=lambda item: item[1], reverse=True)
        kept: list[CandidateProposal] = []
        for box, obj_score in raw_boxes:
            if any(_iou(box, prev.bbox_xywh) > 0.42 for prev in kept):
                continue
            x, y, bw, bh = box
            # Tight context pad (4%) so edge boundary is preserved
            px = max(2, int(0.04 * bw))
            py = max(2, int(0.04 * bh))
            x1 = max(0, x - px)
            y1 = max(0, y - py)
            x2 = min(w, x + bw + px)
            y2 = min(h, y + bh + py)
            crop = bgr_frame[y1:y2, x1:x2].copy()
            kept.append(
                CandidateProposal(
                    bbox_xywh=(x1, y1, x2 - x1, y2 - y1),
                    objectness=obj_score,
                    center_px=(0.5 * (x1 + x2), 0.5 * (y1 + y2)),
                    area_px=(x2 - x1) * (y2 - y1),
                    crop_bgr=crop,
                )
            )
            if len(kept) >= self.settings.max_proposals_per_frame:
                break

        return kept
