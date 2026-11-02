"""Compare native planar/epipolar diagnostics on identical recorded matches."""

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
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.run)
    job = json.loads((root / "app-result.json").read_text())["overview"]["runs"][0]
    target = next(r for r in job["payload"]["references"] if r["object_id"] == job["object_id"])
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for row, view in enumerate(job["views"][:2]):
        candidate = next(c for c in view["candidates"] if c["descriptor_supported"])
        match = candidate["matches"][0]
        images = [cv2.imread(str(root / "store/images" / (sha + ".png"))) for sha in (target["image_shas"][0], candidate["crop_image_sha"])]
        scales = [240 / image.shape[0] for image in images]
        left, right = [cv2.resize(image, (round(image.shape[1] * scale), 240)) for image, scale in zip(images, scales)]
        canvas = cv2.cvtColor(np.concatenate([left, right], axis=1), cv2.COLOR_BGR2RGB)
        a, b = np.array(match["reference_points"]), np.array(match["query_points"])
        _, fundamental_mask = cv2.findFundamentalMat(a, b, cv2.USAC_MAGSAC, 3, .999, 2000)
        if fundamental_mask is None:
            raise ValueError("Native fundamental fit failed; no illustrated substitute.")
        masks = [np.array(match["inlier_mask"], bool), fundamental_mask.ravel().astype(bool)]
        for col, mask in enumerate(masks):
            axis = axes[row, col]
            axis.imshow(canvas)
            for i in np.flatnonzero(mask)[::max(1, int(mask.sum()) // 45)]:
                x, y = a[i] * scales[0], b[i] * scales[1] + [left.shape[1], 0]
                axis.plot([x[0], y[0]], [x[1], y[1]], color="#43a873", linewidth=.7, alpha=.8)
            axis.set_title(f"View {row + 1} · {'recorded single homography' if col == 0 else 'native fundamental-matrix diagnostic'}\n{int(mask.sum())}/{len(mask)} inliers · {mask.mean():.3f} ratio", fontsize=10)
            axis.axis("off")
    fig.suptitle("GEOMETRY DIAGNOSTIC ONLY · identical original DISK/LightGlue correspondences\nApp remains inconclusive; the proposed framework change is not yet integrated", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .93), h_pad=3)
    fig.savefig(args.output, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
