"""Opt-in original matcher execution on recorded crops, with native 3D geometry."""

import argparse
import json
from pathlib import Path

import cv2

from teach_and_find.config import Settings
from teach_and_find.lightglue_adapter import LocalCorrespondence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root, output = Path(args.run), Path(args.output)
    if output.exists():
        raise ValueError("Preserve old evidence; choose a new output file.")
    import torch

    torch.set_num_threads(Settings().vision.torch_threads)
    job = json.loads((root / "app-result.json").read_text())["overview"]["runs"][0]
    target = next(
        r for r in job["payload"]["references"] if r["object_id"] == job["object_id"]
    )
    model = LocalCorrespondence(Settings().search)

    def load(sha):
        image = cv2.imread(str(root / "store/images" / (sha + ".png")))
        if image is None:
            raise ValueError("Recorded model input missing; no replacement.")
        return model.extract(image)

    reference = load(target["image_shas"][0])
    records = []
    for index, view in enumerate(job["views"][:2]):
        candidate = next(c for c in view["candidates"] if c["descriptor_supported"])
        records.append(
            {
                "view": index,
                "crop_image_sha": candidate["crop_image_sha"],
                "reference_sha": target["image_shas"][0],
                "old": candidate["matches"][0],
                "new": model.compare(reference, load(candidate["crop_image_sha"])),
            }
        )
    record = {
        "scope": "actual original DISK/LightGlue re-extraction/matching and native OpenCV on preserved rendered inputs; not fresh navigation",
        "source_run": str(root),
        "provenance": model.provenance,
        "executed_calls": model.calls,
        "comparisons": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(record, stream, indent=2)
    print(
        [
            (r["new"]["inliers"], r["new"]["matches"], r["new"]["supported"])
            for r in records
        ]
    )


if __name__ == "__main__":
    main()
