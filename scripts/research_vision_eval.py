"""Paired raw-proposal/reference-policy evaluation using separate renderer truth.

The custom readout is not an exact-identity classifier. Count its false accepts,
misses and rejected true proposals; do not relabel or correct model outputs.
"""

import argparse
import json
from pathlib import Path


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    base = parser.parse_args().directory
    truth = json.loads((base / "truth.json").read_text())
    captures = {
        r["frame_id"]: r
        for r in map(
            json.loads, (base / "capture-truth.jsonl").read_text().splitlines()
        )
    }
    runs = json.loads((base / "app-runs.json").read_text())
    report = {
        "mode": "synthetic",
        "iou_threshold": 0.5,
        "score_threshold": 0.2,
        "scope": "paired_same_inputs_raw_yoloe_vs_custom_dinov2_reference_policy_not_real_room_quality",
        "matching": "descending_yoloe_score_one_to_one_same_enrollment_class",
        "truth_never_used_by_inference": True,
        "scenes": {},
    }
    for run in runs:
        scene = run["scene"]
        result = run["job"]["result"]
        known = {r["name"] for r in result["references"]}
        entry = {
            "frames": len(result["frames"]),
            "split": truth.get("evaluation_split", {}).get(scene, "development"),
            "mean_frame_elapsed_s": sum(f["elapsed_s"] for f in result["frames"])
            / len(result["frames"]),
            "job_model_elapsed_s": result["elapsed_s"],
            "variants": {},
        }
        for variant in ["raw_yoloe", "dinov2_reference_supported"]:
            tp = fp = fn = truth_count = supported_frames = tracked_tp = switches = (
                proposals
            ) = 0
            last_track, track_ids = {}, {}
            for frame in result["frames"]:
                capture = captures[frame["frame_id"]]
                assert capture["scene"] == scene
                expected = [
                    g
                    for g in truth["scenes"][scene][capture["index"]]
                    if g["key"] in known
                ]
                truth_count += len(expected)
                candidates = [
                    d
                    for d in frame["detections"]
                    if variant == "raw_yoloe"
                    or d.get("reference_comparison", {}).get("decision")
                    == "supported_candidate"
                ]
                supported_frames += bool(candidates)
                proposals += len(candidates)
                matched = set()
                for det in sorted(
                    candidates, key=lambda d: d["model_score"], reverse=True
                ):
                    options = [
                        (iou(det["xyxy"], g["xyxy"]), j)
                        for j, g in enumerate(expected)
                        if j not in matched and g["key"] == det["prompt_name"]
                    ]
                    overlap, index = max(options, default=(0.0, -1))
                    if overlap < 0.5:
                        fp += 1
                        continue
                    tp += 1
                    matched.add(index)
                    track = next(
                        (
                            t
                            for t in frame["tracks"]
                            if t["detection_index"] == det["detection_index"]
                        ),
                        None,
                    )
                    if track:
                        tracked_tp += 1
                        key, tid = det["prompt_name"], track["track_id"]
                        switches += int(key in last_track and last_track[key] != tid)
                        last_track[key] = tid
                        track_ids.setdefault(key, set()).add(tid)
                fn += len(expected) - len(matched)
            entry["variants"][variant] = {
                "ground_truth_enrolled_instances": truth_count,
                "proposals": proposals,
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / truth_count if truth_count else None,
                "frames_with_candidates": supported_frames,
                "tracked_true_positives": tracked_tp,
                "track_id_changes_between_matched_observations": switches,
                "track_ids_by_matched_object": {
                    k: sorted(v) for k, v in track_ids.items()
                },
            }
        report["scenes"][scene] = entry
    (base / "quality.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
