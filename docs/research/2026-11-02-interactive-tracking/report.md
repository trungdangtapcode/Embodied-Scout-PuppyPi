# Interactive target tracking: source-backed research review

Date: 2026-11-02. Research question: how can an operator select an object in the
PuppyPi camera and track it on subsequent incoming frames, with corrections,
visible failures and an honest search/recovery workflow?

**Evidence state: source inspection and remote checkpoint metadata only.** Ten
repositories were cloned and their relevant source inspected. No new tracking
model was installed or executed, no performance benchmark was run, and no new
tracking feature was integrated. Existing combined-model execution remains in
the [earlier report](../2026-11-01-dual-vision-app/report.md). The critical incident
remains OPEN / FAIL.

The resulting [implementation proposal](../../26-interactive-target-tracking.md)
separates the application contract from the research hypotheses. Repository
revisions, inspected file hashes and source links are preserved in
[repository-audit.json](repository-audit.json). Checkpoint availability is a
different evidence state, recorded in [checkpoint-metadata.json](checkpoint-metadata.json).

## 1. The task is interactive video object segmentation

An operator click indicates a target, not a category. A model must resolve the
spatial extent of that target, then use the initialized target representation
on future images. This differs from detecting all objects independently and
assigning temporary IDs to detections. It also differs from identifying an
enrolled physical object after an arbitrary disappearance.

[SAM 2](https://arxiv.org/abs/2408.00714) provides promptable image/video
segmentation. [Cutie](https://arxiv.org/abs/2310.12982) propagates an initial
object mask with learned pixel/object memory. Those are relevant released
components; a handwritten rectangle-motion extrapolator is not a substitute.

The ambiguity of a single point is real: it can indicate a whole object or a
part. [ClickTrack](https://arxiv.org/abs/2411.13183) studies point-to-box
initialization with its Guided Click Refiner. Its paper was found, but an
author-linked usable code/checkpoint release was not verified in this review.
It is related work, not selected implementation reuse. The proposed app instead
offers mask previews, foreground/background clicks and an explicit box tool.

## 2. Prior applications already combine selection and tracking

[IST-ROS](https://github.com/husikl/ist_ros), accompanying
[the SoftwareX paper](https://doi.org/10.1016/j.softx.2024.101979), combines SAM
selection and XMem tracking for camera/robotics use. At revision
`fcce0bb308439d327427cc422ad20c0dfeb27720`, inspected files include
`src/segment_and_track.py` and `src/utils/core_utils.py`. The latter uses the
bundled XMem implementation and custom threshold/contour logic for its center
and detected flag. Its Tk/ROS interface and detection flag should not be copied
as if they established calibrated presence. The root MIT license does not by
itself settle bundled model-code/checkpoint terms.

[DexGraspVLA](https://arxiv.org/abs/2502.20900) is another application precedent.
In its [released source](https://github.com/Psi-Robot/DexGraspVLA/blob/0144c7928817c5149ae836da2682291360828a21/inference.py),
`initialize_sam_cutie` obtains a SAM mask and initializes Cutie; later calls
propagate the mask. It uses original SAM, not SAM 2. Our proposed SAM 2 initializer
is a stated component choice, not a claim to reproduce that paper's full pipeline.
No root LICENSE file was found at that revision, so its application code is not
selected for copying. Neither its VLA policy nor reported robot success transfers
to PuppyPi through reuse of the perception components.

## 3. Candidate audit and decisions

All entries below are **not executed in this research turn**. Published benchmark
speed or quality is not a PuppyPi measurement.

| Candidate | Verified interface/release | Fit and decision |
| --- | --- | --- |
| [SAM 2.1](https://github.com/facebookresearch/sam2) | `build_sam2`, `SAM2ImagePredictor.set_image/predict`; tiny checkpoint metadata available without gating | Proposed initializer for point/box prompts. Its official video path loads a known video length; do not invent an append-frame API |
| [Cutie](https://github.com/hkchengrex/Cutie) | `InferenceCore.step(image, mask, objects)` and subsequent `step(image)`; released `cutie-base-mega.pth` | Proposed sequential live-frame tracker. CPU setup and actual quality remain execution gates |
| [Cutie GUI + RITM](https://github.com/hkchengrex/Cutie/tree/ec5cdd4cf16f75c73ad785a2f96fb97dbad4125a/gui) | Existing interactive GUI and redistributed RITM code/checkpoint | Useful original interactive reference/baseline. Not a silently selected replacement for SAM 2 |
| [SAM 3 / 3.1](https://github.com/facebookresearch/sam3) | Official 3.1 release notes, concept/instance interfaces, gated model metadata | Strong future GPU comparison. Inspected README requires CUDA and gated access; resource-backed video sessions are not an unbounded camera-ingestion API |
| [EdgeTAM](https://github.com/facebookresearch/EdgeTAM) | Released model/project; inspected video predictor still initializes a finite set of frames | Relevant future device deployment experiment; published phone performance is not evidence for our Pi/browser runtime |
| [RealtimeEfficientTAM](https://github.com/AllenNeuralDynamics/RealtimeEfficientTAM) | Community camera adapter with `load_first_frame` and `track` | Has the right streaming shape, but inspected device selection includes CPU substitution when CUDA is requested. Not selected; any experiment must reject missing required devices explicitly |
| [DAM4SAM](https://github.com/jovanavidenovic/DAM4SAM) | Author `initialize(image, init_mask, bbox)` / `track(image)` and released source | Important distractor-aware GPU comparator. Inspected wrapper hardwires CUDA; do not call it CPU-ready |
| [SAM2Long](https://github.com/Mark12Ding/SAM2Long) | Released memory-tree method and modified predictor | Long-clip research comparator; extra hypotheses, finite-video handling and CC BY-NC root license make it unsuitable as an assumed drop-in live backend |
| Current YOLOE → DINOv2 → ByteTrack | Actual prior app runs and failures exist | Preserve as the existing recorded inspection path and research baseline. It is not click-initialized, persistent single-target tracking |

The SAM 3.1 source has a SAM License in `LICENSE`, although its packaging still
contains an MIT classifier. The actual license file governs the audit entry;
an inaccurate classifier must not become the project's provenance statement.

## 4. Why the proposed composition fits the application

SAM 2.1 image prediction accepts pixel-coordinate foreground/background points
and boxes and returns full-resolution masks, predicted mask-quality scores and
low-resolution logits for refinement. An initializer can therefore show what
the click actually selected before the tracking session starts. A mask-quality
score is not a probability that the target is the named physical object.

Cutie's original `InferenceCore` consumes a new image at each `step` and retains
object memory. It returns per-pixel segmentation scores; `output_prob_to_mask`
maps them to the tracked object IDs. The app can therefore keep one processor
for one camera/target generation instead of rerunning disconnected 12-frame
jobs. A new generation must get a new processor: `clear_memory()` alone retains
the object manager and other processor state.

The proposed composition is a **project integration of original implementations**.
It is not a new pretrained model, the Cutie author's SAM 2 pipeline, a VLA,
autonomous navigation, or learned world modeling. Added lifecycle/health/search
policy must be disclosed as project-owned logic.

## 5. Source-level execution traps to resolve first

1. Cutie's `get_default_model()` downloads two assets, calls `.cuda()` and uses
   `torch.load` without explicit CPU mapping. The main constructor also loads
   pretrained ResNet-18/50 assets. Setup must provision every declared artifact;
   the worker must start without network and fail if any is missing. A custom
   loader may configure original `CUTIE` and load its weights; it must not replace
   the original `InferenceCore`, encoders or mask decoder.
2. The upstream Cutie package includes GUI/training dependencies such as PySide6
   and a Git dependency. Isolate an audited inference dependency lock in a future
   `.venv-tracking/`; do not install that stack into the host or current vision
   environment. Python/PyTorch compatibility has not been demonstrated here.
3. Use SAM 2's explicit image-predictor path, not an unverified camera fork. Freeze
   postprocessing choices before testing. A CPU profile can explicitly configure
   no CUDA-extension hole/sprinkle processing; it may not catch a required-kernel
   error and switch methods. The image masks still come from original inference.
4. Cutie updates sensory/working memory during `step`; it is not safe to claim
   that an application rejects a suspicious mask *before* upstream memory update.
   End the generation on health failure, or separately propose and evaluate an
   actual memory-update change. Do not describe an unimplemented rollback.
5. `force_permanent=True` changes what enters permanent memory. The initial
   approved mask may be retained; never promote every predicted mask or a search
   candidate into trusted permanent memory implicitly.
6. Neither normal mask softmax nor DINOv2 cosine is a calibrated presence/re-ID
   probability. A plausible wrong mask may survive. Health-monitor limitations
   must remain visible, including undetected drift.

## 6. Checkpoint facts and missing evidence

Remote metadata at the observed SAM 2 model revision
`de431c4043854a71d8101e17995dfe596bf101a5` lists
`sam2.1_hiera_tiny.pt`, 156,008,466 bytes, with LFS SHA256
`7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`.
That is remote metadata, **not an independently checked download**.

Cutie's v1.0 release lists `cutie-base-mega.pth`, 140,443,788 bytes. Its author
downloader expects MD5 `a6071de6136982e396851903ab4c083a`; a downloaded SHA256
has not been measured here. ResNet constructor assets and their download digests
are also unresolved setup work. These are required preflight tasks, not permission
to run with randomly initialized or substituted weights.

## 7. Evaluation must separate initialization, propagation and identity

Use the original [DAVIS evaluation implementation](https://github.com/davisvideochallenge/davis2017-evaluation)
at `ac7c43fca936f9722837b7fbd337d284ba37004b`: `db_eval_iou` and
`db_eval_boundary` for J/F. Its code is BSD-3-Clause; public video/annotation
licenses must be checked independently. No DAVIS data was downloaded in this turn.

Measure user-prompt initialization separately from an evaluator-GT-mask
propagation baseline. GT masks are legitimate only in the clearly labeled
semi-supervised benchmark arm, never in the deployed target-selection path.
Measure all future frames after a prompt and count failed initialization.

[Long-term tracking evaluation](https://arxiv.org/abs/1804.07056) motivates
including out-of-view/absent frames and recovery quality. J/F alone does not
establish correct absence, absence cause, identity continuity or recovery after
a camera gap. Reuse an official long-term evaluator if its metric is claimed;
otherwise label the app's recovery metrics as custom measures.

The inspected 108-file/53-distinct synthetic set is development evidence. It is
too short/static to establish a live tracker. New long sequences, distinct
calibration/test episodes, negative intervals, near-identical distractors and
real-camera tests are mandatory before a quality claim. Planned experiments,
thresholds, release gates and figure requirements are specified in the proposal.

## 8. Research outcome

Recommended first experiment: original SAM 2.1 tiny image initialization plus
original Cutie base-mega sequential inference, with no robot actuation. Compare
mask propagation, initialization burden, failures and measured deployment latency
against the existing pipeline and a labeled original interactive baseline.

The recommendation is based on the inspected input interfaces, available assets,
runtime separation and application fit. It is **not a measured assertion that
this combination is the most accurate or fast enough on our CPU**. The first
implementation gate must execute the actual upstream components before an app
session is described as working. No fallback closes a failed gate.
