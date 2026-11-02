"""Opt-in LPIPS development diagnostic, never a search backend or quality pass.

Original pretrained LPIPS measures resized crop/reference distance. Resizing does
not solve view alignment or occlusion. No acceptance threshold or identity
decision is produced, and no app/search/memory state is modified.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from teach_and_find.model_artifacts import verified_checkout

REVISION = "082bb24f84c091ea94de2867d34c4544f68e0963"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = verified_checkout(args.source, REVISION, "LPIPS")
    sys.path.insert(0, str(source))
    import lpips
    import torch

    if not Path(lpips.__file__).resolve().is_relative_to(source):
        raise RuntimeError("Original LPIPS import is shadowed.")
    torch.set_num_threads(2)
    model = lpips.LPIPS(net="squeeze", spatial=True).eval()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    with torch.inference_mode():
        example = [
            lpips.im2tensor(lpips.load_image(str(source / "imgs" / name)))
            for name in ("ex_ref.png", "ex_p0.png")
        ]
        example_map = model(*example)
        for run in args.runs:
            root = Path(run)
            job = json.loads((root / "app-result.json").read_text())["overview"][
                "runs"
            ][0]
            references = next(
                r
                for r in job["payload"]["references"]
                if r["object_id"] == job["object_id"]
            )["image_shas"]

            def tensor(sha):
                image = cv2.imread(str(root / "store/images" / (sha + ".png")))
                if image is None:
                    raise ValueError("Recorded image missing: " + sha)
                return lpips.im2tensor(
                    cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (256, 256))
                )

            for index, view in enumerate(job["views"]):
                for candidate in view["candidates"]:
                    if not candidate["descriptor_supported"]:
                        continue
                    crop = tensor(candidate["crop_image_sha"])
                    comparisons = []
                    for reference in references:
                        started = time.monotonic()
                        distance = model(tensor(reference), crop)[0, 0].numpy()
                        name = f"{root.name}-view{index}-candidate{candidate['detection_index']}-{reference[:8]}.npy"
                        np.save(output / name, distance)
                        comparisons.append(
                            {
                                "reference_sha": reference,
                                "mean_distance": float(distance.mean()),
                                "seconds": time.monotonic() - started,
                                "spatial_map": name,
                            }
                        )
                    records.append(
                        {
                            "run": str(root),
                            "view": index,
                            "crop_image_sha": candidate["crop_image_sha"],
                            "comparisons": comparisons,
                        }
                    )
    weights = Path(torch.hub.get_dir()) / "checkpoints/squeezenet1_1-b8a52dc0.pth"
    result = {
        "status": "development_diagnostic_only_no_identity_decision_or_app_integration",
        "repository": "https://github.com/richzhang/PerceptualSimilarity",
        "revision": REVISION,
        "license": "BSD-2-Clause",
        "entry_point": "lpips.LPIPS(net='squeeze', spatial=True).forward",
        "weights_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (weights, source / "lpips/weights/v0.1/squeeze.pth")
        },
        "torch": torch.__version__,
        "device": "cpu",
        "paid_api_calls": 0,
        "preprocessing": "custom RGB resize256; original im2tensor normalization to [-1,1]; unaligned inputs",
        "original_example": {
            "shape": list(example_map.shape),
            "mean": float(example_map.mean()),
        },
        "comparisons": records,
    }
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "comparisons": len(records),
                "original_example": result["original_example"],
            }
        )
    )


if __name__ == "__main__":
    main()
