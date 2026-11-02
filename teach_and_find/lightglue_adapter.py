"""Original pretrained DISK/LightGlue with local, hash-verified weights only."""

from pathlib import Path
import importlib.metadata
import sys
from contextlib import contextmanager

import cv2
import numpy as np

from teach_and_find.errors import AssistantError
from teach_and_find.model_artifacts import verified_weights
from teach_and_find.search_navigation import LIGHTGLUE_REVISION, pinned_source

WEIGHTS = {
    "depth-save.pth": "9c2ee4ded238892dfa51569941372601e35e4a74aa6f84ea80053d2ab1c07abe",
    "disk_lightglue_v0-1_arxiv.pth": "b5b21d47ea24f2c5e501aec9c91b9716e4c8c3429a4dc1e615c133c4c9378335",
}


@contextmanager
def local_checkpoint_transport(torch, loader):
    """Constrain original constructors' URL loader to verified local files.

    This isolated worker initializes models serially. Only weight transport is
    adapted; extractor/matcher constructors, tensors and forward code stay original.
    Unknown URLs raise, and no network/baseline substitute is attempted.
    """
    original = torch.hub.load_state_dict_from_url
    torch.hub.load_state_dict_from_url = loader
    try:
        yield
    finally:
        torch.hub.load_state_dict_from_url = original


class LocalCorrespondence:
    def __init__(self, cfg):
        import torch

        self.cfg = cfg
        source = pinned_source(cfg.lightglue_source, LIGHTGLUE_REVISION)
        files = {
            name: verified_weights(str(Path(cfg.weights) / name), sha, "SEARCH")
            for name, sha in WEIGHTS.items()
        }
        sys.path.insert(0, str(source))
        import lightglue
        from lightglue import DISK, LightGlue
        from lightglue.utils import numpy_image_to_torch, rbd

        if not Path(lightglue.__file__).resolve().is_relative_to(source):
            raise AssistantError(
                "SEARCH_SOURCE_MISMATCH", "LightGlue import is shadowed."
            )

        def local_weight(url, *args, **kwargs):
            if (
                url
                == "https://raw.githubusercontent.com/cvlab-epfl/disk/master/depth-save.pth"
            ):
                name = "depth-save.pth"
            elif (
                url
                == "https://github.com/cvg/LightGlue/releases/download/v0.1_arxiv/disk_lightglue.pth"
            ):
                name = "disk_lightglue_v0-1_arxiv.pth"
            else:
                raise AssistantError(
                    "SEARCH_UNKNOWN_CHECKPOINT",
                    "Unexpected checkpoint request; network is forbidden.",
                )
            return torch.load(files[name], map_location="cpu", weights_only=False)

        # Replace weight transport only; run original constructors/forward methods.
        with local_checkpoint_transport(torch, local_weight):
            self.extractor = DISK(max_num_keypoints=cfg.keypoints).eval().cpu()
            self.matcher = LightGlue(features="disk", flash=False).eval().cpu()
        # Upstream renames its older transformer keys. Check every learned tensor
        # against the released checkpoint, so strict=False cannot leave random layers.
        checkpoint = torch.load(
            files["disk_lightglue_v0-1_arxiv.pth"],
            map_location="cpu",
            weights_only=False,
        )
        for i in range(self.matcher.conf.n_layers):
            checkpoint = {
                k.replace(f"self_attn.{i}", f"transformers.{i}.self_attn").replace(
                    f"cross_attn.{i}", f"transformers.{i}.cross_attn"
                ): v
                for k, v in checkpoint.items()
            }
        for name, parameter in self.matcher.named_parameters():
            if name not in checkpoint or not torch.equal(
                parameter.detach(), checkpoint[name]
            ):
                raise AssistantError(
                    "SEARCH_WEIGHTS_INCOMPLETE", f"Unverified learned parameter: {name}"
                )
        self.tensor, self.rbd, self.torch = numpy_image_to_torch, rbd, torch
        self.calls = {"DISK.forward": 0, "LightGlue.forward": 0}
        self.provenance = {
            "repository": "https://github.com/cvg/LightGlue",
            "revision": LIGHTGLUE_REVISION,
            "weights": WEIGHTS,
            "features": "original_kornia_DISK_depth",
            "device": "cpu",
            "packages": {
                name: importlib.metadata.version(name)
                for name in ("torch", "kornia", "kornia-rs")
            },
            "resize": cfg.resize,
            "max_keypoints": cfg.keypoints,
            "policy": "custom_geometric_correspondence_v1_not_calibrated_identity_probability",
        }

    def extract(self, image):
        with self.torch.inference_mode():
            features = self.extractor.extract(
                self.tensor(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)),
                resize=self.cfg.resize,
            )
        self.calls["DISK.forward"] += 1
        return features

    def compare(self, reference, query):
        with self.torch.inference_mode():
            output = self.matcher({"image0": reference, "image1": query})
        self.calls["LightGlue.forward"] += 1
        first, second, result = map(self.rbd, [reference, query, output])
        matches = result["matches"].cpu().numpy()
        a = first["keypoints"].cpu().numpy()[matches[:, 0]]
        b = second["keypoints"].cpu().numpy()[matches[:, 1]]
        inliers = np.zeros(len(matches), dtype=bool)
        homography = None
        if len(matches) >= 4:
            homography, mask = cv2.findHomography(
                a, b, cv2.RANSAC, 3.0, maxIters=2000, confidence=0.995
            )
            if mask is not None:
                inliers = mask.reshape(-1).astype(bool)
        coverage = 0.0
        if inliers.sum() >= 3:
            width, height = first["image_size"].cpu().numpy()
            coverage = float(
                cv2.contourArea(cv2.convexHull(a[inliers].astype(np.float32)))
                / (width * height)
            )
        ratio = float(inliers.mean()) if len(inliers) else 0.0
        accepted = (
            int(inliers.sum()) >= self.cfg.min_inliers
            and ratio >= self.cfg.min_inlier_ratio
            and coverage >= self.cfg.min_coverage
        )
        return {
            "matches": len(matches),
            "inliers": int(inliers.sum()),
            "inlier_ratio": ratio,
            "reference_coverage": coverage,
            "supported": accepted,
            "reference_points": a.tolist(),
            "query_points": b.tolist(),
            "inlier_mask": inliers.tolist(),
            "homography": homography.tolist() if homography is not None else None,
            "score_semantics": "custom_geometric_support_not_identity_probability",
        }
