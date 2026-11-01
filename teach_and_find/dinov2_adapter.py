"""Real DINOv2 feature extraction plus explicitly custom reference comparison.

This is not an upstream exact-identity classifier. Its hand-selected cosine and
margin policy only supports candidates, never confirms an exact identity.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image

from teach_and_find.config import VisionSettings
from teach_and_find.model_artifacts import verified_checkout, verified_weights
from teach_and_find.storage import AssistantError, EvidenceStore


def verify_dinov2(cfg: VisionSettings) -> dict:
    source = verified_checkout(cfg.descriptor_source, cfg.descriptor_revision, "DINOV2")
    verified_weights(cfg.descriptor_checkpoint, cfg.descriptor_sha256, "DINOV2")
    return {
        "repository": "https://github.com/facebookresearch/dinov2",
        "revision": cfg.descriptor_revision,
        "model": cfg.descriptor_model,
        "checkpoint_sha256": cfg.descriptor_sha256,
        "checkpoint_source": "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth",
        "digest_basis": "observed_official_download_digest_not_author_published_digest",
        "license": "Apache-2.0 for this DINOv2 model/code profile",
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
        "preprocessing": "upstream_make_classification_eval_transform_RGB_resize256_bicubic_centercrop224_ImageNet_normalization",
        "decision_policy": {
            "implementation": "project_owned_max_reference_cosine_and_margin_v1",
            "threshold_origin": "hand_selected_development_policy_not_calibrated",
            "minimum_similarity": cfg.reference_similarity_threshold,
            "minimum_margin": cfg.reference_margin_threshold,
            "requires_detector_and_descriptor_class_agreement": True,
            "exact_identity_verified": False,
        },
    }


def compare_reference_scores(
    scores: list[list[float]],
    references: list[dict],
    prompt_id: str,
    cfg: VisionSettings,
) -> dict:
    """Declared custom readout of genuine model cosines, with no hidden labels."""
    if len(scores) != len(references) or not references:
        raise AssistantError(
            "DINOV2_OUTPUT_INVALID", "Every reference class must be compared."
        )
    classes = []
    for ref, values in zip(references, scores):
        if (
            len(values) != len(ref["image_shas"])
            or not values
            or not all(math.isfinite(v) and -1.00001 <= v <= 1.00001 for v in values)
        ):
            raise AssistantError(
                "DINOV2_OUTPUT_INVALID", "Invalid reference similarity values."
            )
        best = max(range(len(values)), key=values.__getitem__)
        classes.append(
            {
                "object_id": ref["object_id"],
                "name": ref["name"],
                "score": values[best],
                "best_reference_sha": ref["image_shas"][best],
                "per_reference": [
                    {"image_sha": sha, "cosine": v}
                    for sha, v in zip(ref["image_shas"], values)
                ],
            }
        )
    if len(classes) != len(references) or not classes:
        raise AssistantError(
            "DINOV2_OUTPUT_INVALID", "Every reference class must be compared."
        )
    ranked = sorted(classes, key=lambda c: c["score"], reverse=True)
    best = ranked[0]
    # A single enrolled class has no measured inter-class margin. It still needs
    # the absolute similarity gate and does not establish novelty/identity.
    margin = best["score"] - ranked[1]["score"] if len(ranked) > 1 else None
    prompt = next((c for c in classes if c["object_id"] == prompt_id), None)
    if prompt is None:
        raise AssistantError(
            "DINOV2_OUTPUT_INVALID",
            "Detector prompt is not in the frozen reference set.",
        )
    if best["object_id"] != prompt_id:
        reason = "detector_descriptor_disagreement"
    elif best["score"] < cfg.reference_similarity_threshold:
        reason = "insufficient_reference_similarity"
    elif margin is not None and margin < cfg.reference_margin_threshold:
        reason = "ambiguous_reference_comparison"
    else:
        reason = "reference_policy_satisfied_not_identity_confirmation"
    return {
        "decision": "supported_candidate"
        if reason == "reference_policy_satisfied_not_identity_confirmation"
        else "unresolved",
        "reason": reason,
        "best_object_id": best["object_id"],
        "best_name": best["name"],
        "best_reference_sha": best["best_reference_sha"],
        "best_score": best["score"],
        "prompt_score": prompt["score"],
        "margin": margin,
        "classes": classes,
        "score_semantics": "uncalibrated_cosine_not_probability",
        "policy_implementation": "custom_max_cosine_and_margin_not_an_upstream_identity_classifier",
        "exact_identity_verified": False,
    }


class DinoReferenceComparator:
    def __init__(
        self, cfg: VisionSettings, store: EvidenceStore, references: list[dict], check
    ):
        if cfg.descriptor_model != "dinov2_vits14":
            raise AssistantError(
                "DINOV2_MODEL_UNSUPPORTED", "Unknown descriptor model; no substitute."
            )
        self.cfg, self.check, self.references = cfg, check, references
        self.provenance = verify_dinov2(cfg)
        source = Path(cfg.descriptor_source).expanduser().resolve()
        sys.path.insert(0, str(source))
        try:
            import torch
            from dinov2.data.transforms import make_classification_eval_transform
            import dinov2
        except ImportError as error:
            raise AssistantError(
                "DINOV2_DEPENDENCY_MISSING",
                f"Required DINOv2 dependency is missing: {error}",
            ) from error
        if not Path(dinov2.__file__).resolve().is_relative_to(source):
            raise AssistantError(
                "DINOV2_SOURCE_MISMATCH",
                "Another DINOv2 package shadowed the pinned source.",
            )
        self.torch = torch
        self.transform = make_classification_eval_transform()
        # The upstream loader caches even file:// URLs. Verify that cache too,
        # so a stale same-named weights file cannot bypass digest validation.
        cache = store.root / "dinov2-cache"
        torch.hub.set_dir(str(cache))
        cached = cache / "checkpoints" / Path(cfg.descriptor_checkpoint).name
        if cached.exists():
            verified_weights(str(cached), cfg.descriptor_sha256, "DINOV2_CACHE")
        self.model = (
            torch.hub.load(
                str(source),
                cfg.descriptor_model,
                source="local",
                pretrained=True,
                weights=str(Path(cfg.descriptor_checkpoint).expanduser().resolve()),
            )
            .to(cfg.device)
            .eval()
        )
        verified_weights(str(cached), cfg.descriptor_sha256, "DINOV2_CACHE")
        self.provenance["cache_sha256_verified"] = True
        self.reference_embeddings = []
        for ref in references:
            self.check()
            self.reference_embeddings.append(
                self.embed([store.load_image(sha) for sha in ref["image_shas"]])
            )

    def embed(self, images: list[np.ndarray]):
        torch = self.torch
        result = []
        for offset in range(0, len(images), self.cfg.descriptor_batch_size):
            self.check()
            batch_images = images[offset : offset + self.cfg.descriptor_batch_size]
            if any(im is None or im.size == 0 for im in batch_images):
                raise AssistantError(
                    "DINOV2_INPUT_INVALID", "Empty crop; no replacement image."
                )
            batch = torch.stack(
                [
                    self.transform(Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)))
                    for im in batch_images
                ]
            ).to(self.cfg.device)
            with torch.inference_mode():
                features = self.model(batch)
                if (
                    features.shape != (len(batch_images), 384)
                    or not torch.isfinite(features).all()
                    or (features.norm(dim=-1) < 1e-8).any()
                ):
                    raise AssistantError(
                        "DINOV2_OUTPUT_INVALID",
                        "The required backbone returned invalid descriptors.",
                    )
                result.append(torch.nn.functional.normalize(features, dim=-1))
        return torch.cat(result, dim=0)

    def compare(self, crops: list[np.ndarray], prompt_ids: list[str]) -> list[dict]:
        if not crops:
            return []
        features = self.embed(crops)
        similarities = [
            (features @ ref.T).cpu().tolist() for ref in self.reference_embeddings
        ]
        return [
            compare_reference_scores(
                [s[i] for s in similarities], self.references, oid, self.cfg
            )
            for i, oid in enumerate(prompt_ids)
        ]
