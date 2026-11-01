# Vision failure attribution: models execute, the identity method is insufficient

Date: 2026-11-02. Inspected revision: `96d9fcd`. Read-only diagnosis; no runtime,
threshold, model, fixture or acceptance criterion was changed. The fatal review
remains OPEN / FAIL. This diagnosis does not assign a new delivery score.

The user asked whether the failed recognition comes from YOLOE, DINOv2, ByteTrack,
the author repositories/papers, project code or hardcoded/fallback substitutes.
The evidence distinguishes execution, project decision logic and task quality.

## Directly demonstrated loss by stage

Recomputed one-to-one IoU/class matches against the existing evaluator-only truth
for the actual recorded app outputs. Counts are frame/object observations, not
independent objects or real-room success rates.

| Condition | Expected enrolled observations | Correct YOLOE proposals | Retained by custom reference rule | Additional true proposals rejected by rule |
| --- | ---: | ---: | ---: | ---: |
| Moving | 33 | 32 | 25 | 7 |
| Novel angle | 36 | 36 | 15 | 21 |
| Changed view | 36 | 26 | 26 | 0 |
| Novel lighting | 36 | 23 | 23 | 0 |

All seven extra moving-scene rejections concern the green object: six fail the
hand-selected similarity threshold and one fails the margin. All 21 extra
novel-angle rejections fail similarity (12 target-box and nine green-object
observations). One correct green candidate has cosine `0.7887195348739624`, is
ranked as the correct class, but fails the project cutoff `0.80`. This is not a
calibrated probability or a DINOv2-provided identity decision.

YOLOE output itself misses ten changed-view and thirteen novel-lighting instances.
The current evidence localizes those losses before descriptor filtering, but
cannot attribute their deeper cause to the model versus custom reference contact
sheets, prompt preparation, configuration or synthetic-domain fit. No controlled
prompt/crop ablation or author benchmark reproduction settles that question.

## Fresh independent execution checks

[Results](evidence/2026-11-02-vision-diagnosis/independent-results.json),
[reproducer](evidence/2026-11-02-vision-diagnosis/independent-probe.py),
[input/source hashes](evidence/2026-11-02-vision-diagnosis/manifest.json).

- Verified both pinned source revisions/clean tracked source and checkpoint digests.
- Independently invoked the original DINOv2 Hub model, original evaluation transform,
  normalization and dot products without using the project's comparator. Across
  three selected stored crops/reference sets, maximum absolute cosine discrepancy
  was `5.960464477539063e-08`. This supports numerical agreement for these samples;
  it does not prove every integration path is bug-free or that features solve identity.
- Checked 324 saved candidate crops against their declared source PNG rectangles:
  zero pixel mismatches. This does not validate the quality of YOLOE's boxes.
- Replayed actual upstream ByteTrack with identical settings/recorded detections.
  On the novel-angle scene raw detections yielded 36 correct tracked observations
  and 24 false tracked observations; the recorded reference gate yielded 13 correct
  and zero false tracked observations. On moving input those counts were 26/22 raw
  versus 22/0 gated. This is a short controlled tracking-input replay, not a general
  tracker benchmark. The project prefilter removes measurements before ByteTrack;
  running real ByteTrack does not undo that loss or establish reference identity.
- Re-rendered the genuine target under exactly the alias fixture's camera/scene
  parameters. Its RGB image equals the stored indistinguishable-front decoy image
  pixel for pixel; maximum channel difference is zero. Different hidden faces/IDs
  are evaluator truth. This deliberately ambiguous input requires more evidence
  before exact identity, which the current app does not autonomously acquire.

The reproducer requires the prepared CPU vision environment and the ignored raw
acceptance dataset. It performs inference/replay only, never actuates a robot,
calls a paid API or changes production behavior. No long-running child remains.

## Responsibility and what is not established

The project owns the input contact-sheet adaptation, crop binding, choice of global
DINOv2 descriptors, maximum-reference cosine, fixed `0.80`/`0.05` thresholds, model-
agreement gate and filtering before ByteTrack. These are not an author's released
exact-instance verification pipeline. Their inadequate task quality is a project
method/design limitation; using real models does not establish the promised verifier.

There is fixed/custom logic: thresholds, reference preparation and scripted
simulation inputs. In the inspected version-2 vision path these do not replace a
missing learned model with a heuristic or canned result. Original model forward
calls and independent numerical agreement support actual inference. The earlier
eight real source/weights/cache/profile failures have null results, not substitute
predictions. This scoped finding is not a claim that every other repo feature is
learned, nor a universal absence-of-bugs certificate.

The [YOLOE paper](https://arxiv.org/abs/2503.07465) addresses prompted detection and
segmentation; the [DINOv2 paper](https://arxiv.org/abs/2304.07193) supplies general
visual features; the [ByteTrack paper](https://arxiv.org/abs/2110.06864) addresses
association in multi-object tracking. The author DINOv2 model card describes
retrieval/classification uses. None of these execution checks reproduces all paper
benchmarks or establishes the project's exact-instance requirement. There is no
current evidence warranting a conclusion that an author repository or paper is
wrong. Programming bugs remain possible beyond the specifically checked paths.

No threshold was lowered to fit inspected evaluation scenes. The next design must
address reference/crop/prompt suitability, an evaluated rejection/verification
policy and acquisition of discriminative views for ambiguous observations, under
an agreed revision. More passing software tests alone cannot satisfy that quality
gate. The existing app remains a genuine model-backed candidate system with
unresolved exact-identity acceptance.

## Subsequent visual evidence

The [visual atlas](../research/2026-11-01-dual-vision-app/figures/README.md) and
[figure PDF](../research/2026-11-01-dual-vision-app/figures/figures.pdf) now show
all nine conditions, actual model masks/boxes, failure crops/reference comparisons,
error/recall trade-offs and stage losses. A complete local gallery covers all 103
recorded model frames. This is visualization of existing evidence, not a method
change, new inference or a passed identity-quality gate.
