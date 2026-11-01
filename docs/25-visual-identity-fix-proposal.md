# Visual identity follow-up: executed probe, proposed application stage

Date: 2026-11-01. Status: **Accepted proposal / implementation next**. User confirmation of this
pipeline revision was received after clarifying that both models are complementary. Do not rewrite YOLOE acceptance to make the current
recognition errors pass. The critical incident remains OPEN / FAIL.

## Why another stage is necessary

The [actual YOLOE app](24-yoloe-vision.md) executes genuine visual-prompt inference
and ByteTrack, but detects a wall marker as an enrolled object and proposes a
look-alike as the target. This is a category/candidate proposal path, not reliable
exact-instance verification. The original custom appearance baseline cannot
substitute for the missing learned comparison. Raising a threshold on the same
evaluated scenes or blacklisting AprilTag pixels would not establish the requested
capability.

## Verified upstream and genuine probe

[DINOv2 paper](https://arxiv.org/abs/2304.07193),
[author source](https://github.com/facebookresearch/dinov2), revision
`7764ea0f912e53c92e82eb78a2a1631e92725fc8`. The selected ViT-S/14 code and
model card specify Apache-2.0. This does not describe newer Cell-DINO or XRay-DINO
assets, which have different terms.

Actual entry points executed on CPU: `torch.hub.load(source="local")`,
`dinov2_vits14`, original `make_classification_eval_transform` and
`DinoVisionTransformer.forward`. The official checkpoint is
`https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth`,
88,283,115 bytes, observed SHA256
`b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9`.
This digest was computed from the downloaded official asset; it is not claimed
to be an author-published checksum. No training, local GPU or VLM API was used.

The research script extracted genuine 384-dimensional descriptors for enrolled
references and 13 YOLOE-generated crops from the first frames of development
scenes. Project-owned maximum cosine over reference descriptors is the declared
readout. It is not a pretrained identity classifier, a calibrated probability,
or the author's instance-verification pipeline. No threshold or identity verdict
was applied. On this probe, a correct blue crop scored about 0.916 against blue
references, a correct target about 0.866, and the decoy crop about 0.619 against
target references. Background/crop contamination still produces substantial
similarity. These examples motivate an experiment, not a quality claim.

Reproduce after separately preparing the pinned DINOv2 source and checkpoint:

```bash
PYTHONPATH=. CUDA_VISIBLE_DEVICES=-1 MPLBACKEND=Agg .venv-vision/bin/python \
  scripts/research_dinov2_probe.py \
  --directory runs/vision-app-2026-11-01-acceptance \
  --source .upstream/dinov2 \
  --checkpoint data/models/dinov2/dinov2_vits14_pretrain.pth \
  --output runs/my-new-dinov2-probe
```

The script verifies source revision, clean tracked source and weights digest;
missing or mismatched artifacts fail. It records source hashes and actual
cosines. Raw probe evidence is linked from the [execution report](research/2026-11-01-yoloe-app/report.md).
Its source directory and the checkpoint are not installed by `vision-setup`,
imported by the app, or invoked by the production vision worker.

## Proposed revision requiring agreement

Keep YOLOE as the genuine proposal/segmentation model. For each model-generated
`CandidateProposal`, run the pinned DINOv2 backbone and compare its descriptor
against the explicitly enrolled multi-view reference images. Persist raw YOLOE
outputs and per-reference descriptor similarities, including rejected candidates.
Keep ByteTrack associations distinct from any identity decision; tracking cannot
turn repeated misclassification into confirmed identity.

The feature extractor would be **actual DINOv2 source/model reuse**. The cosine,
margin, multi-view aggregation and rejection policy would be **custom decision
logic**, disclosed as such from the outset. Do not claim reuse of an exact-instance
paper's full algorithm or formal calibration without implementing/evaluating it.
No confirmed observation should be emitted until the accepted identity/abstention
gate passes. A missed proposal remains unresolved; DINOv2 cannot recover an object
which YOLOE never proposed.

Before promoting quality, freeze reference/query preprocessing and a calibration
protocol. Separate calibration and evaluation by rendered trajectory/view/lighting
condition; retain distinct unknown/decoy cases and unseen real-room evaluation.
Keep the inspected development scenes out of claims of held-out quality. Report
proposal recall, comparison false accepts/rejects, end-to-end precision/recall,
abstention, track coverage/switches and CPU latency at paired budgets. Include
identical-front/hidden-side cases that must remain inconclusive. Compare against
raw YOLOE and the explicitly named appearance baseline; do not silently use either
when a required learned component fails.

The revised app profile would require both verified checkpoints, fail if either
component is unavailable, and identify each model plus the custom readout at its
point of use. No public-quality result, automatic inspection, autonomous search,
navigation or predictive world model is delivered by this proposal or probe.
