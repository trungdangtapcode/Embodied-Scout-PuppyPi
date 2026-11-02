"""Plot actual pre/post geometry records without rerunning or inventing matches."""

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
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    evidence = json.loads(Path(args.evidence).read_text())
    root = Path(evidence["source_run"])
    rows = evidence["comparisons"]
    figure, axes = plt.subplots(
        len(rows), 2, figsize=(13, 4.5 * len(rows)), squeeze=False
    )
    for row, record in enumerate(rows):
        images = [
            cv2.imread(str(root / "store/images" / (record[key] + ".png")))
            for key in ("reference_sha", "crop_image_sha")
        ]
        if any(image is None for image in images):
            raise ValueError("Recorded input missing; no illustrated substitute.")
        scales = [240 / image.shape[0] for image in images]
        left, right = [
            cv2.resize(image, (round(image.shape[1] * scale), 240))
            for image, scale in zip(images, scales)
        ]
        canvas = cv2.cvtColor(np.concatenate([left, right], axis=1), cv2.COLOR_BGR2RGB)
        for col, label in enumerate(("old", "new")):
            actual = record[label]
            a, b = (
                np.array(actual["reference_points"]),
                np.array(actual["query_points"]),
            )
            mask = np.array(actual["inlier_mask"], bool)
            axis = axes[row, col]
            axis.imshow(canvas)
            for index in np.flatnonzero(mask)[:: max(1, int(mask.sum()) // 45)]:
                x, y = a[index] * scales[0], b[index] * scales[1] + [left.shape[1], 0]
                axis.plot(
                    [x[0], y[0]],
                    [x[1], y[1]],
                    color="#43a873",
                    linewidth=0.7,
                    alpha=0.8,
                )
            axis.set_title(
                f"View {record['view'] + 1} · {'recorded planar fit' if label == 'old' else 'actual original matcher + native fundamental fit'}\n{actual['inliers']}/{actual['matches']} inliers · support={actual['supported']}",
                fontsize=10,
            )
            axis.axis("off")
    figure.suptitle(
        "ACTUAL RENDERED-INPUT REGRESSION · original DISK / LightGlue re-executed\nNative OpenCV geometry; unchanged support thresholds; geometry alone does not prove identity",
        fontsize=12,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93), h_pad=3)
    figure.savefig(args.output, dpi=140)
    plt.close(figure)


if __name__ == "__main__":
    main()
