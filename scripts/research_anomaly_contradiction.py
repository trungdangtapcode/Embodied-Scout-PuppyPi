"""Run the ORIGINAL AnomalyDINO notebook scoring function on recorded app crops.

Research only: no app backend, threshold, identity verdict or memory mutation.
The upstream notebook function is extracted verbatim, not reimplemented. Only
torch.hub source/weight transport is redirected to verified pinned local files.
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

from teach_and_find.config import Settings
from teach_and_find.model_artifacts import verified_checkout, verified_weights

REVISION = "b9d1c2648e3a5247437d4d953d907a8f3d994457"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = verified_checkout(args.source, REVISION, "ANOMALYDINO")
    cfg = Settings().vision
    backbone = verified_checkout(
        cfg.descriptor_source, cfg.descriptor_revision, "DINOV2"
    )
    weights = verified_weights(
        cfg.descriptor_checkpoint, cfg.descriptor_sha256, "DINOV2"
    )
    sys.path.insert(0, str(source))
    import cv2
    import faiss
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import torch
    from src.backbones import get_model
    from src.detection import augment_image

    torch.set_num_threads(2)
    faiss.omp_set_num_threads(2)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    notebook = source / "demo_AnomalyDINO.ipynb"
    cells = [
        "".join(c["source"])
        for c in json.loads(notebook.read_text())["cells"]
        if c["cell_type"] == "code"
        and "".join(c["source"]).startswith("def score_single_image(")
    ]
    if len(cells) != 1:
        raise RuntimeError("Pinned upstream notebook entry point changed.")
    namespace = {"np": np, "faiss": faiss, "augment_image": augment_image}
    exec(compile(cells[0], str(notebook) + ":score_single_image", "exec"), namespace)
    score = namespace["score_single_image"]
    original_load = torch.hub.load

    def load_local(repo, model, *a, **kw):
        if repo != "facebookresearch/dinov2" or model != "dinov2_vits14" or a or kw:
            raise RuntimeError("Unexpected upstream model request; no alternate model.")
        return original_load(
            str(backbone), model, source="local", pretrained=True, weights=str(weights)
        )

    torch.hub.load = load_local
    try:
        model = get_model("dinov2_vits14", "cpu", smaller_edge_size=672)
    finally:
        torch.hub.load = original_load
    samples, records = [], []
    for run in args.runs:
        root = Path(run)
        job = json.loads((root / "app-result.json").read_text())["overview"]["runs"][0]
        references = next(
            r
            for r in job["payload"]["references"]
            if r["object_id"] == job["object_id"]
        )["image_shas"]

        def load(sha):
            image = cv2.imread(str(root / "store/images" / (sha + ".png")))
            if image is None:
                raise ValueError("Missing recorded image: " + sha)
            return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        images_ref = [load(sha) for sha in references]
        for index, view in enumerate(job["views"]):
            # Same actual supported candidates as the explicitly paired LPIPS probe.
            for candidate in view["candidates"]:
                if not candidate["descriptor_supported"]:
                    continue
                image = load(candidate["crop_image_sha"])
                for masking in (False, True):
                    started = time.monotonic()
                    value, distances, mask = score(
                        image,
                        images_ref,
                        model,
                        masking=masking,
                        rotation=False,
                        use_faiss=True,
                    )
                    name = f"sample-{len(records)}"
                    np.save(output / (name + "-map.npy"), distances)
                    np.save(output / (name + "-mask.npy"), mask)
                    records.append(
                        {
                            "run": str(root),
                            "view": index,
                            "crop_image_sha": candidate["crop_image_sha"],
                            "reference_shas": references,
                            "masking": masking,
                            "rotation": False,
                            "original_top1percent_score": float(value),
                            "foreground_fraction": float(mask.mean()),
                            "seconds": time.monotonic() - started,
                            "map": name + "-map.npy",
                            "mask": name + "-mask.npy",
                        }
                    )
                    samples.append((image, distances))
    fig, axes = plt.subplots(
        2, len(samples), figsize=(3 * len(samples), 6), squeeze=False
    )
    vmax = max(float(distance.max()) for _, distance in samples)
    for i, ((image, distance), record) in enumerate(zip(samples, records)):
        axes[0, i].imshow(image)
        axes[0, i].set_title(
            f"{'Unknown fixture' if 'unknown-hidden' in record['run'] else 'Target fixture'}\nActual view {record['view'] + 1}; mask={record['masking']}",
            fontsize=9,
        )
        im = axes[1, i].imshow(distance, vmin=0, vmax=vmax, cmap="magma")
        axes[1, i].set_title(
            f"Original top-1%: {record['original_top1percent_score']:.4f}\n{record['seconds']:.2f}s; no identity decision",
            fontsize=9,
        )
        for row in axes:
            row[i].axis("off")
    fig.suptitle(
        "DEVELOPMENT DIAGNOSTIC · original AnomalyDINO notebook + pinned pretrained DINOv2 · CPU\nEvaluator fixture names label panels only; they never enter scoring. No quality pass or app integration."
    )
    fig.colorbar(
        im,
        ax=list(axes[1]),
        fraction=0.015,
        label="Original patch cosine distance (not probability)",
    )
    fig.savefig(output / "maps.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    result = {
        "status": "original_notebook_scoring_executed_development_only",
        "repository": "https://github.com/dammsi/AnomalyDINO",
        "revision": REVISION,
        "license": "Apache-2.0",
        "entry_point": "verbatim demo_AnomalyDINO.ipynb:score_single_image",
        "function_sha256": hashlib.sha256(cells[0].encode()).hexdigest(),
        "backbone_revision": cfg.descriptor_revision,
        "backbone_checkpoint_sha256": cfg.descriptor_sha256,
        "device": "cpu",
        "smaller_edge_size": 672,
        "paid_api_calls": 0,
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "torch",
                "torchvision",
                "numpy",
                "opencv-python",
                "scipy",
                "faiss-cpu",
                "scikit-learn",
            )
        },
        "comparisons": records,
    }
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"comparisons": len(records), "status": result["status"]}))


if __name__ == "__main__":
    main()
