"""Explicit custom multi-view geometry policy over genuine learned outputs.

This is not IEVE, a calibrated identity probability or a predictive world model.
All registered reference views must have local learned correspondence support.
"""

import math
import numpy as np


def assess_views(views, target_id, reference_count, calibration, cfg):
    candidates = []
    for index, view in enumerate(views):
        for detection in view["candidates"]:
            if (
                detection["object_id"] != target_id
                or not detection["descriptor_supported"]
                or detection["floor_xy"] is None
            ):
                continue
            supported = {
                m["reference_index"] for m in detection["matches"] if m["supported"]
            }
            if supported:
                candidates.append(
                    {
                        "view": index,
                        "detection": detection["detection_index"],
                        "floor_xy": detection["floor_xy"],
                        "references": supported,
                        "pose": view["pose"],
                    }
                )
    clusters = []
    for candidate in candidates:
        for cluster in clusters:
            # Complete-link spatial association: cannot chain disjoint objects.
            if all(
                math.dist(candidate["floor_xy"], c["floor_xy"])
                <= cfg.association_radius_m
                for c in cluster
            ):
                cluster.append(candidate)
                break
        else:
            clusters.append([candidate])
    qualified = []
    for cluster in clusters:
        distinct = len({c["view"] for c in cluster}) >= 2
        baseline = max(
            (
                math.dist(
                    [a["pose"]["x"], a["pose"]["y"]], [b["pose"]["x"], b["pose"]["y"]]
                )
                for a in cluster
                for b in cluster
            ),
            default=0.0,
        )
        coverage = set().union(*(c["references"] for c in cluster))
        if (
            not distinct
            or baseline < cfg.min_view_baseline_m
            or len(coverage) != reference_count
        ):
            continue
        xy = np.mean([c["floor_xy"] for c in cluster], axis=0).tolist()
        regions = [
            s["id"]
            for s in calibration["stations"]
            if math.dist(s["center"], xy) <= s["radius_m"]
        ]
        if len(regions) == 1:
            qualified.append(
                {
                    "station": regions[0],
                    "floor_xy": xy,
                    "baseline_m": baseline,
                    "evidence": [
                        {**c, "references": sorted(c["references"])} for c in cluster
                    ],
                }
            )
    if len(qualified) == 1:
        return {
            "verdict": "confirmed",
            "policy": "custom_multiview_geometry_v1",
            **qualified[0],
        }
    return {
        "verdict": "inconclusive",
        "reason": "multiple_supported_instances"
        if len(qualified) > 1
        else "insufficient_distinct_view_reference_or_location_support",
        "candidate_count": len(candidates),
        "policy": "custom_multiview_geometry_v1",
        "absence_established": False,
    }
