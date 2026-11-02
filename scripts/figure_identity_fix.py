"""Plot genuine replay patch evidence and the original versus revised verdict."""

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
    parser.add_argument("--replay", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.replay)
    data = json.loads((root / "result.json").read_text())
    examples = [
        (view, candidate)
        for view in data["views"]
        for candidate in view["candidates"]
        if "appearance" in candidate
    ]
    if not examples:
        raise ValueError("No executed appearance evidence; no illustrative substitute.")
    fig, axes = plt.subplots(
        len(examples), 3, figsize=(12, 4.6 * len(examples)), squeeze=False
    )
    for row, (view, candidate) in enumerate(examples):
        appearance = candidate["appearance"]
        images = [
            cv2.imread(str(root / "store/images" / (sha + ".png")))
            for sha in (appearance["reference_shas"][0], candidate["crop_image_sha"])
        ]
        for col, image in enumerate(images):
            axes[row, col].imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            axes[row, col].axis("off")
        axes[row, 0].set_title("Supplied target reference (not a query label)")
        axes[row, 1].set_title(
            "Actual previously captured model crop\nDINOv2 cosine "
            + str(round(candidate["reference_comparison"]["best_score"], 4))
        )
        distances = np.load(root / "store" / appearance["map_file"])
        im = axes[row, 2].imshow(distances, vmin=0, vmax=2, cmap="magma")
        axes[row, 2].axis("off")
        axes[row, 2].set_title(
            f"Original AnomalyDINO, no masking\nTop-1% distance {appearance['score']:.4f}; rejected={appearance['appearance_rejected']}"
        )
        fig.colorbar(
            im,
            ax=axes[row, 2],
            fraction=0.04,
            label="Patch cosine distance, not probability",
        )
    fig.suptitle(
        f"ACTUAL MODEL REPLAY · old: {data['old_readout']['verdict']} → revised: {data['new_readout']['verdict']}\n{data['new_readout'].get('reason', 'retained positive evidence')} · No fresh navigation or general identity-quality claim",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92), h_pad=4.5, w_pad=1.5)
    fig.savefig(args.output, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
