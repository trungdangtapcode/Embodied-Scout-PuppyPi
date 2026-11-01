# Visual identity follow-up: executed probe, proposed application stage

Date: 2026-11-01. Status: **Accepted and integrated execution subset; exact-identity quality unverified**. User confirmation of this
pipeline revision was received after clarifying that both models are complementary. Do not rewrite YOLOE acceptance to make the current
recognition errors pass. The critical incident remains OPEN / FAIL. The original probe/proposal below is retained; see the [combined app execution](research/2026-11-01-dual-vision-app/report.md) for the later implementation.

## Why another stage is necessary

The original [raw-YOLOE profile](research/2026-11-01-yoloe-app/report.md) executed genuine visual-prompt inference
and ByteTrack, but detected a wall marker as an enrolled object and proposed a
look-alike as the target. This is a category/candidate proposal path, not reliable
exact-instance verification. The original custom appearance baseline cannot
substitute for the learned comparison missing at that stage. Raising a threshold on the same
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
At probe time the app did not use this backbone. The probe script remains
research-only; the subsequently implemented production adapter now uses the same
pinned source/checkpoint, both prepared by `vision-setup`. See the combined report
for that separate application execution.

## Original proposal, subsequently accepted

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


## Accepted revision and actual application integration

The user clarified that YOLOE and DINOv2 are complementary and requested both.
The combined profile now executes YOLOE proposals/segmentation, original DINOv2
reference/crop descriptors, the explicitly custom maximum-cosine/margin rule and
original Ultralytics ByteTrack over supported candidates. Both pretrained models
are mandatory; their real execution and failures are in the
[combined report](research/2026-11-01-dual-vision-app/report.md).

The fixed development policy is similarity ≥ 0.80 and top-class margin ≥ 0.05
when multiple classes exist, with detector/descriptor class agreement. These
hand-selected thresholds were declared before the new-condition experiment;
they are not fitted calibration or an author's exact-instance method. All raw
proposals/rejections stay in the API/app. No verified identity, absence, continuous
room state or predictive world-model claim follows. The scope of the historical
research-only script remains a probe; the separate production adapter now supplies
the actual app integration.
