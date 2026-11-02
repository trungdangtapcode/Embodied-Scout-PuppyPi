"""Explicit custom multi-view geometry policy over genuine learned outputs.

This is not IEVE, a calibrated identity probability or a predictive world model.
All registered reference views must have local learned correspondence support.
"""

import math
import numpy as np
from teach_and_find.errors import AssistantError

ANOMALY_FUNCTION_SHA = (
    "45d4135040305ffef3933766eb2021ede369964146f9d9e5aac37d2773293f5d"
)


def assess_views(views, target_id, reference_count, calibration, cfg):
    if cfg.profile_version not in {2, 3, 4}:
        raise AssistantError(
            "SEARCH_PROFILE_UNSUPPORTED", "Unknown verification policy; no fallback."
        )
    appearance_required = cfg.profile_version in {3, 4}
    policy = (
        "original_anomalydino_native_fundamental_multiview_v3"
        if cfg.profile_version == 4
        else
        "custom_multiview_geometry_with_original_anomalydino_v2"
        if appearance_required
        else "custom_multiview_geometry_v1"
    )
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
            if cfg.profile_version == 4 and any(
                m.get("geometry_model") != "fundamental_usac_magsac"
                for m in detection["matches"]
            ):
                raise AssistantError(
                    "SEARCH_GEOMETRY_EVIDENCE_REQUIRED",
                    "Search v4 requires native fundamental geometry; historical planar matches cannot substitute.",
                )
            if supported:
                appearance = detection.get("appearance")
                if appearance_required and (
                    not isinstance(appearance, dict)
                    or type(appearance.get("appearance_rejected")) is not bool
                    or not isinstance(appearance.get("score"), (int, float))
                    or not math.isfinite(appearance["score"])
                    or appearance.get("crop_image_sha")
                    != detection.get("crop_image_sha")
                    or appearance.get("provenance", {}).get("function_sha256")
                    != ANOMALY_FUNCTION_SHA
                    or appearance.get("provenance", {}).get("calibration_sha256")
                    != cfg.anomaly_calibration_sha256
                ):
                    raise AssistantError(
                        "SEARCH_APPEARANCE_EVIDENCE_REQUIRED",
                        "Required original appearance inference is missing or inconsistent; geometric agreement cannot substitute.",
                    )
                candidates.append(
                    {
                        "view": index,
                        "detection": detection["detection_index"],
                        "floor_xy": detection["floor_xy"],
                        "references": supported,
                        "pose": view["pose"],
                        "appearance_rejected": appearance["appearance_rejected"]
                        if appearance_required
                        else False,
                        **({"appearance": appearance} if appearance_required else {}),
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
    rejected_clusters = 0
    for cluster in clusters:
        if any(c["appearance_rejected"] for c in cluster):
            rejected_clusters += 1
            continue
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
            "policy": policy,
            **qualified[0],
        }
    return {
        "verdict": "inconclusive",
        "reason": "multiple_supported_instances"
        if len(qualified) > 1
        else "appearance_not_supported_by_references"
        if rejected_clusters
        else "insufficient_distinct_view_reference_or_location_support",
        "candidate_count": len(candidates),
        "appearance_rejected_clusters": rejected_clusters,
        "policy": policy,
        "absence_established": False,
    }
