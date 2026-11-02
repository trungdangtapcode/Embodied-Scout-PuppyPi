"""Plot actual original appearance evidence from a completed rendered-input app run."""

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
    candidate = next(
        c for v in job["views"] for c in v["candidates"] if c.get("appearance")
    )
    assessment = candidate["appearance"]
    images = [
        cv2.imread(str(root / "store/images" / (sha + ".png")))
        for sha in (assessment["reference_shas"][0], candidate["crop_image_sha"])
    ]
    if any(im is None for im in images):
        raise ValueError("Actual evidence missing; no illustrated substitute.")
    fig, axes = plt.subplots(1, 3, figsize=(13, 5))
    for ax, im in zip(axes[:2], images):
        ax.imshow(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
        ax.axis("off")
    axes[0].set_title("Actual supplied target reference")
    axes[1].set_title(
        f"Actual model proposal crop\nDINOv2 cosine {candidate['reference_comparison']['best_score']:.4f}\nNative geometry supports {sum(m['supported'] for m in candidate['matches'])} reference views"
    )
    plotted = axes[2].imshow(
        np.load(root / "store" / assessment["map_file"]), vmin=0, vmax=2, cmap="magma"
    )
    axes[2].set_title(
        f"Original AnomalyDINO, no PCA masking\nDistance {assessment['score']:.4f}; veto={assessment['appearance_rejected']}"
    )
    axes[2].axis("off")
    fig.colorbar(
        plotted, ax=axes[2], fraction=0.04, label="Patch distance, not probability"
    )
    verdict = (job["model_readout"] or job["result"])["verdict"]
    fig.suptitle(
        f"ACTUAL RENDERED-INPUT APP EVIDENCE · final readout: {verdict}\nShared-surface geometry is insufficient; required original appearance inference is retained",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.86), w_pad=2)
    fig.savefig(args.output, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
