"""Visualize a recorded false confirmation; no model outputs are synthesized."""

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
    parser.add_argument("run")
    parser.add_argument("output")
    args = parser.parse_args()
    root = Path(args.run)
    job = json.loads((root / "app-result.json").read_text())["overview"]["runs"][0]
    result = next(
        json.loads(event["record_json"])["result"]
        for event in job["events"]
        if event["kind"] == "verification_evaluated"
    )
    references = next(
        ref
        for ref in job["payload"]["references"]
        if ref["object_id"] == job["object_id"]
    )["image_shas"]

    def load(sha):
        image = cv2.imread(str(root / "store/images" / (sha + ".png")))
        if image is None:
            raise ValueError("Recorded image is missing: " + sha)
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    figure = plt.figure(figsize=(12, 10))
    grid = figure.add_gridspec(3, 6)
    for index, sha in enumerate(references):
        axis = figure.add_subplot(grid[0, 2 * index : 2 * index + 2])
        axis.imshow(load(sha))
        axis.set_title(f"Supplied target reference {index + 1}", fontsize=10)
        axis.axis("off")
    for column, evidence in enumerate(result["evidence"][:2]):
        view = job["views"][evidence["view"]]
        candidate = next(
            item
            for item in view["candidates"]
            if item["detection_index"] == evidence["detection"]
        )
        crop = load(candidate["crop_image_sha"])
        axis = figure.add_subplot(grid[1, column * 3 : column * 3 + 3])
        axis.imshow(crop)
        cosine = candidate["reference_comparison"]["best_score"]
        axis.set_title(
            f"Actual unknown-object crop, view {evidence['view'] + 1}\nDINOv2 cosine {cosine:.4f}; no competing enrolled class",
            fontsize=10,
        )
        axis.axis("off")
        match = candidate["matches"][column * 2]
        reference = load(references[match["reference_index"]])
        height = 230
        scales = [height / image.shape[0] for image in (reference, crop)]
        left, right = [
            cv2.resize(image, (round(image.shape[1] * scale), height))
            for image, scale in zip((reference, crop), scales)
        ]
        axis = figure.add_subplot(grid[2, column * 3 : column * 3 + 3])
        axis.imshow(np.concatenate([left, right], axis=1))
        inliers = np.flatnonzero(match["inlier_mask"])
        for index in inliers[:: max(1, len(inliers) // 40)]:
            a = np.array(match["reference_points"][index]) * scales[0]
            b = np.array(match["query_points"][index]) * scales[1] + [left.shape[1], 0]
            axis.plot(
                [a[0], b[0]], [a[1], b[1]], color="#2f9d64", linewidth=0.7, alpha=0.7
            )
        axis.set_title(
            f"Original DISK/LightGlue: {match['inliers']} inliers\nMatching shared appearance does not verify differing surfaces",
            fontsize=10,
        )
        axis.axis("off")
    figure.suptitle(
        "FAIL · SYNTHETIC HELD-OUT UNKNOWN OBJECT · actual model false confirmation\n"
        "Readout confirmed Station_A; qualification gate blocked automatic memory",
        fontsize=13,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(args.output, dpi=150)
    plt.close(figure)


if __name__ == "__main__":
    main()
