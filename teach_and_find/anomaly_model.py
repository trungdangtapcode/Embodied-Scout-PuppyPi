"""Direct pinned AnomalyDINO notebook execution; no rewritten anomaly algorithm.

Imported only in the isolated optional CPU process. The project supplies source/
weight transport, records and a disclosed fitted scalar application classifier.
"""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

from teach_and_find.errors import AssistantError
from teach_and_find.model_artifacts import verified_checkout, verified_weights

REVISION = "b9d1c2648e3a5247437d4d953d907a8f3d994457"
FUNCTION_SHA = "45d4135040305ffef3933766eb2021ede369964146f9d9e5aac37d2773293f5d"


def fit_decision(record):
    """Use the real framework fit/predict; never hand-reimplement its tree."""
    from sklearn.tree import DecisionTreeClassifier
    import numpy as np

    if record.get("schema_version") != 1 or not record.get("samples"):
        raise AssistantError("ANOMALY_CALIBRATION_INVALID", "Missing development fit.")
    samples = record["samples"]
    x = np.asarray([[sample["score"]] for sample in samples], dtype=float)
    y = np.asarray([sample["appearance_rejected"] for sample in samples], dtype=int)
    if not np.isfinite(x).all() or set(y.tolist()) != {0, 1}:
        raise AssistantError(
            "ANOMALY_CALIBRATION_INVALID",
            "Finite positive and negative development samples are required.",
        )
    decision = DecisionTreeClassifier(max_depth=1, random_state=0).fit(x, y)
    if not np.array_equal(decision.predict(x), y):
        raise AssistantError(
            "ANOMALY_CALIBRATION_FAILED",
            "The declared scalar model does not separate development data; no substitute.",
        )
    fitted = {
        "threshold": decision.tree_.threshold.tolist(),
        "feature": decision.tree_.feature.tolist(),
        "values": decision.tree_.value.tolist(),
    }
    if "fitted_tree" in record and record["fitted_tree"] != fitted:
        raise AssistantError(
            "ANOMALY_CALIBRATION_REPRODUCTION_FAILED",
            "Original framework fit does not reproduce the frozen artifact.",
        )
    return decision


class OriginalAnomalyDino:
    def __init__(self, cfg, vision):
        source = verified_checkout(cfg.anomaly_source, REVISION, "ANOMALYDINO")
        backbone = verified_checkout(
            vision.descriptor_source, vision.descriptor_revision, "DINOV2"
        )
        weights = verified_weights(
            vision.descriptor_checkpoint, vision.descriptor_sha256, "DINOV2"
        )
        sys.path.insert(0, str(source))
        import numpy as np
        import faiss
        import torch
        from src.backbones import get_model
        from src.detection import augment_image

        torch.set_num_threads(vision.torch_threads)
        faiss.omp_set_num_threads(vision.torch_threads)
        notebook = source / "demo_AnomalyDINO.ipynb"
        cells = [
            "".join(c["source"])
            for c in json.loads(notebook.read_text())["cells"]
            if c["cell_type"] == "code"
            and "".join(c["source"]).startswith("def score_single_image(")
        ]
        if (
            len(cells) != 1
            or hashlib.sha256(cells[0].encode()).hexdigest() != FUNCTION_SHA
        ):
            raise AssistantError(
                "ANOMALY_SOURCE_MISMATCH",
                "Original scoring code differs from the inspected pinned function.",
            )
        namespace = {"np": np, "faiss": faiss, "augment_image": augment_image}
        exec(
            compile(cells[0], str(notebook) + ":score_single_image", "exec"), namespace
        )
        self.score_function = namespace["score_single_image"]
        self.score_calls = 0
        original_load = torch.hub.load

        def local_load(repo, name, *args, **kwargs):
            if (
                repo != "facebookresearch/dinov2"
                or name != "dinov2_vits14"
                or args
                or kwargs
            ):
                raise AssistantError(
                    "ANOMALY_MODEL_REQUEST_INVALID",
                    "Unexpected original model request; no substitute.",
                )
            return original_load(
                str(backbone),
                name,
                source="local",
                pretrained=True,
                weights=str(weights),
            )

        torch.hub.load = local_load
        try:
            self.model = get_model(
                "dinov2_vits14", "cpu", smaller_edge_size=cfg.anomaly_resolution
            )
        finally:
            torch.hub.load = original_load
        # Original torch.hub can reuse a same-named cache file. Check the actual
        # loaded tensors against the hash-verified release, not only its path.
        expected_state = torch.load(weights, map_location="cpu", weights_only=True)
        actual_state = self.model.model.state_dict()
        if actual_state.keys() != expected_state.keys() or any(
            not torch.equal(actual_state[name].cpu(), tensor)
            for name, tensor in expected_state.items()
        ):
            raise AssistantError(
                "ANOMALY_LOADED_CHECKPOINT_MISMATCH",
                "Actual loaded tensors differ from the verified release; stale cache cannot substitute.",
            )
        loaded_tensors = len(actual_state)
        del expected_state
        self.provenance = {
            "repository": "https://github.com/dammsi/AnomalyDINO",
            "revision": REVISION,
            "function_sha256": FUNCTION_SHA,
            "entry_point": "verbatim demo_AnomalyDINO.ipynb:score_single_image",
            "license": "Apache-2.0",
            "device": "cpu",
            "backbone_revision": vision.descriptor_revision,
            "checkpoint_sha256": vision.descriptor_sha256,
            "loaded_state_verified": True,
            "loaded_state_tensors": loaded_tensors,
            "resolution": cfg.anomaly_resolution,
            "masking": False,
            "rotation": False,
            "packages": {
                name: importlib.metadata.version(name)
                for name in (
                    "torch",
                    "torchvision",
                    "numpy",
                    "faiss-cpu",
                    "scikit-learn",
                    "opencv-python",
                )
            },
        }

    def score(self, image_rgb, references_rgb):
        result = self.score_function(
            image_rgb,
            references_rgb,
            self.model,
            masking=False,
            rotation=False,
            use_faiss=True,
        )
        self.score_calls += 1
        return result
