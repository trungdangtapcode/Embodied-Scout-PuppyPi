"""Research-only DINOv2 feature probe; never changes app predictions or confirms identity.

Reuse the author's ViT-S/14 and evaluation transform. The maximum reference
cosine readout is explicitly project-owned comparison logic, not a released
instance-verification algorithm. No decision threshold is fitted or applied.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image

from teach_and_find.storage import EvidenceStore


REVISION = "7764ea0f912e53c92e82eb78a2a1631e92725fc8"
WEIGHTS_SHA256 = "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        required=True,
        help="Existing rendered app acceptance run",
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, weights, output = (
        args.source.resolve(),
        args.checkpoint.resolve(),
        args.output.resolve(),
    )
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        parser.error("DINOv2 source revision mismatch; no alternate implementation.")
    subprocess.run(
        ["git", "-C", str(source), "diff", "--exit-code", "HEAD"], check=True
    )
    if hashlib.sha256(weights.read_bytes()).hexdigest() != WEIGHTS_SHA256:
        parser.error("DINOv2 weights mismatch; no replacement.")
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(CUDA_VISIBLE_DEVICES="-1", TORCH_HOME=str(output / "cache"))
    sys.path.insert(0, str(source))
    import torch
    from dinov2.data.transforms import make_classification_eval_transform

    torch.set_num_threads(2)
    transform = make_classification_eval_transform()
    model = torch.hub.load(
        str(source), "dinov2_vits14", source="local", weights=str(weights)
    ).eval()

    @torch.inference_mode()
    def embed(images):
        batch = torch.stack(
            [
                transform(Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)))
                for im in images
            ]
        )
        return torch.nn.functional.normalize(model(batch), dim=-1)

    base = args.directory.resolve()
    runs = json.loads((base / "app-runs.json").read_text())
    references = runs[0]["job"]["result"]["references"]
    records = []
    with EvidenceStore(base / "state") as store:
        embeddings = [
            embed([store.load_image(sha) for sha in ref["image_shas"]])
            for ref in references
        ]
        for run in runs:
            # Deliberately a small exploratory sample, not held-out evaluation.
            frame = run["job"]["result"]["frames"][0]
            image = store.load_image(frame["image_sha"])
            for detection in frame["detections"]:
                x1, y1, x2, y2 = np.asarray(detection["xyxy"]).astype(int)
                crop = image[
                    max(0, y1) : min(image.shape[0], y2),
                    max(0, x1) : min(image.shape[1], x2),
                ]
                if crop.size == 0:
                    raise RuntimeError("Invalid model crop; no substitute input.")
                features = embed([crop])
                records.append(
                    {
                        "scene": run["scene"],
                        "frame_id": frame["frame_id"],
                        "detection_index": detection["detection_index"],
                        "image_sha": frame["image_sha"],
                        "xyxy": detection["xyxy"],
                        "yoloe_prompt_name": detection["prompt_name"],
                        "reference_max_cosines": {
                            ref["name"]: float((features @ emb.T).max())
                            for ref, emb in zip(references, embeddings)
                        },
                    }
                )
    manifest = {
        "scope": "research_probe_not_integrated_identity_verifier",
        "device": "cpu",
        "repository": "https://github.com/facebookresearch/dinov2",
        "revision": revision,
        "license": "Apache-2.0 for this DINOv2 model/code profile",
        "model": "dinov2_vits14",
        "checkpoint_source": "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth",
        "checkpoint_sha256": WEIGHTS_SHA256,
        "digest_basis": "observed_download_digest_not_author_published_digest",
        "entry_points": [
            "torch.hub.load(source=local)",
            "dinov2_vits14",
            "make_classification_eval_transform",
            "DinoVisionTransformer.forward",
        ],
        "files_sha256": {
            p: hashlib.sha256((source / p).read_bytes()).hexdigest()
            for p in [
                "hubconf.py",
                "dinov2/hub/backbones.py",
                "dinov2/models/vision_transformer.py",
                "dinov2/data/transforms.py",
            ]
        },
        "embedding_dimension": 384,
        "readout": "custom_max_reference_cosine_no_threshold_no_probability",
        "warning": "Development scenes already inspected. No calibrated rejection, accuracy advantage or exact-identity guarantee.",
        "records": records,
    }
    (output / "probe.json").write_text(json.dumps(manifest, indent=2))
    print(
        f"Actual DINOv2 features for {len(records)} crops written to {output / 'probe.json'}; not app integration."
    )


if __name__ == "__main__":
    main()
