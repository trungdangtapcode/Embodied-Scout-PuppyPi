"""Show actual diagnostic learned matches, separately from supported app verdicts."""
import argparse
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    probe = json.loads(Path(args.probe).read_text())
    root = Path(args.run)
    run = json.loads((root / "app-result.json").read_text())["overview"]["runs"][0]
    target = next(ref for ref in run["payload"]["references"] if ref["object_id"] == run["object_id"])
    reference = cv2.imread(str(root / "store/images" / (target["image_shas"][1] + ".png")))
    fig, axes = plt.subplots(2, 1, figsize=(10, 9))
    for axis, proposal in zip(axes, probe[0][:2]):
        detection = proposal["detection"]
        crop = cv2.imread(str(root / "store/images" / (detection["crop_image_sha"] + ".png")))
        match = proposal["matches"][1]
        height = 260
        left_scale, right_scale = height / reference.shape[0], height / crop.shape[0]
        left, right = [cv2.resize(image, (round(image.shape[1] * scale), height)) for image, scale in [(reference, left_scale), (crop, right_scale)]]
        canvas = np.concatenate([left, right], axis=1)
        axis.imshow(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
        good = np.flatnonzero(match["inlier_mask"])
        for index in good[::max(1, len(good)//40)]:
            a = np.array(match["reference_points"][index]) * left_scale
            b = np.array(match["query_points"][index]) * right_scale + [left.shape[1], 0]
            axis.plot([a[0], b[0]], [a[1], b[1]], color="#2f9d64", linewidth=.7, alpha=.65)
        axis.axis("off")
        axis.set_title(f"Enrollment reference → actual YOLOE crop · {match['inliers']}/{match['matches']} RANSAC inliers\nGeometric support: {match['supported']} · app class-agreement decision: {detection['reference_comparison']['decision']}", fontsize=10)
    fig.suptitle("DEVELOPMENT DIAGNOSTIC · original pretrained DISK + LightGlue\nSelected raw crops; neither panel establishes an accepted target-finding feature", fontsize=12)
    fig.tight_layout(); fig.savefig(args.output, dpi=160); plt.close(fig)


if __name__ == "__main__":
    main()
