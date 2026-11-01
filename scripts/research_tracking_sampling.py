"""Paired original-Cutie inference: sequential versus sampled same-input replay.

Mask agreement is not accuracy. Inputs are authored renderer images and the seed
is actual original SAM inference from an explicitly authored box. No paid calls.
"""

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket

import cv2
import numpy as np
from PIL import Image

from teach_and_find.config import Settings
from teach_and_find.tracking_models import TrackingModels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve existing evidence; use a new output directory.")
    args.output.mkdir(parents=True)

    def reject_network(*args, **kwargs):
        raise RuntimeError("NETWORK_FORBIDDEN_IN_TRACKING_REPLAY")

    socket.socket.connect = reject_network
    cfg = replace(Settings().tracking, enabled=True, device="cpu")
    models = TrackingModels(cfg)
    sources = [args.inputs / f"moving-{i}.png" for i in range(12)]
    frames = [cv2.imread(str(p)) for p in sources]
    if any(f is None for f in frames):
        raise RuntimeError("Required exact replay inputs missing; no substitution.")
    # Authored box covers the left rendered box in this historical input profile.
    prompt = {"points": [], "labels": [], "box": [100, 140, 235, 265]}
    previews, elapsed = models.preview(frames[0], prompt)
    selected = int(np.argmax([score for _, score in previews]))
    seed = previews[selected][0]
    Image.fromarray(seed * 255).save(args.output / "sam-seed.png")
    arms = {}
    timings = {}
    schedules = {"ordered": list(range(12)), "sampled": [0, 2, 4, 6, 8, 10, 11]}
    for name, indices in schedules.items():
        models.reset()
        masks = {}
        steps = []
        directory = args.output / name
        directory.mkdir()
        for i in indices:
            mask, step = models.step(frames[i], seed if i == 0 else None)
            masks[i] = mask
            steps.append(step)
            Image.fromarray(mask * 255).save(directory / f"mask-{i}.png")
        arms[name] = masks
        timings[name] = steps
    agreement = []
    for i in schedules["sampled"]:
        left = arms["ordered"][i] > 0
        right = arms["sampled"][i] > 0
        union = int((left | right).sum())
        intersection = int((left & right).sum())
        agreement.append(
            {
                "frame_index": i,
                "mask_iou_agreement": intersection / union if union else None,
                "ordered_foreground_pixels": int(left.sum()),
                "sampled_foreground_pixels": int(right.sum()),
            }
        )
    result = {
        "input": "authored_render_replay_not_real_room",
        "method": "actual_original_sam21_cutie",
        "sampling_policy": "fixed_every_second_frame_for_paired_component_diagnostic_not_live_scheduler",
        "seed_prompt_source": "authored_operator_box",
        "seed_prompt": prompt,
        "selected_preview": selected,
        "sam_elapsed_s": elapsed,
        "sam_scores": [s for _, s in previews],
        "schedules": schedules,
        "step_seconds": timings,
        "agreement": agreement,
        "ground_truth_accuracy": "NOT_EVALUATED",
        "provenance": models.provenance,
        "inputs": [
            {"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sources
        ],
    }
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    cv2.imwrite(str(args.output / "first-source.png"), frames[0])
    cv2.imwrite(str(args.output / "last-source.png"), frames[-1])
    print(
        json.dumps(
            {
                "compared_frames": len(agreement),
                "agreement": [x["mask_iou_agreement"] for x in agreement],
                "accuracy": "not evaluated",
            }
        )
    )


if __name__ == "__main__":
    main()
