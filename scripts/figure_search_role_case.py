"""Render an actual paired replay capture/crop and its measured role decisions."""
import argparse
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = json.loads(Path(args.replay).read_text())
    root = Path(args.store) / "images"
    def image(sha):
        return cv2.cvtColor(cv2.imread(str(root / (sha + ".png"))), cv2.COLOR_BGR2RGB)
    before = result["profiles"][0]["frames"][0]["detections"]
    after = result["profiles"][1]["frames"][0]["detections"]
    # Select the highest actual target-gallery score; no evaluator truth box/ID.
    candidates = [d for d in after if d["reference_comparison"]["best_object_id"] == result["target_id"]]
    chosen = max(candidates, key=lambda d: d["reference_comparison"]["best_score"])
    previous = next(d for d in before if d["crop_image_sha"] == chosen["crop_image_sha"])
    score = chosen["reference_comparison"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), gridspec_kw={"width_ratios": [1.7, 1, 1]})
    axes[0].imshow(image(result["frame"]["image_sha"]))
    x0, y0, x1, y1 = chosen["xyxy"]
    axes[0].add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=False, edgecolor="#00ba96", linewidth=2))
    axes[0].set_title("Actual app capture\nBox coordinates from original YOLOE", fontsize=11)
    axes[1].imshow(image(score["best_reference_sha"]))
    axes[1].set_title("Closest enrolled reference\n" + score["best_name"], fontsize=11)
    axes[2].imshow(image(chosen["crop_image_sha"]))
    axes[2].set_title("Actual model crop\nRaw YOLOE label: " + chosen["prompt_name"], fontsize=11)
    for axis in axes:
        axis.axis("off")
    fig.suptitle(f"Same capture, gallery and released weights · DINO cosine {score['best_score']:.5f}, margin {score['margin']:.5f}\nv2: {previous['reference_comparison']['decision']} → v3: {score['decision']} (candidate only, not final memory)", fontsize=13)
    fig.text(.5, .035, "SYNTHETIC CAPTURE + ACTUAL ORIGINAL-MODEL REPLAY · no target truth/box supplied to inference", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .06, 1, .88)); fig.savefig(args.output, dpi=160); plt.close(fig)


if __name__ == "__main__":
    main()
