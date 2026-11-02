# Identity decision correction: execution contract

Date: 2026-11-02. The user explicitly instructed implementation of the identity
fix after reviewing the failed custom decision and AnomalyDINO diagnostics.
This authorizes the proposed genuine AnomalyDINO integration; it does not waive
the quality gate or establish success. Historical search v2 remains failed.

## Method fixed before implementation

- Preserve actual YOLOE proposals, DINOv2 gallery candidates, DISK/LightGlue
  correspondence, AprilTag localization and PythonRobotics motion.
- Require original AnomalyDINO notebook `score_single_image`, pinned author
  revision `b9d1c2648e3a5247437d4d953d907a8f3d994457`, its original DINOv2 wrapper
  and pinned ViT-S/14 checkpoint. Use CPU FAISS, edge 672, no rotation augmentation
  and **no PCA masking**. All resulting model patches remain evidence; the
  original resize and crop to patch-size multiples remain unchanged. Background/
  occlusion can cause abstention and cannot silently be removed for acceptance.
- Preserve the complete original scoring function, including reference-patch
  memory, normalized FAISS distances and top-1% aggregation. Project code loads
  original source, transports records and retains maps/provenance. No handwritten
  nearest-neighbor/scoring approximation replaces it.
- Fit an original scikit-learn `DecisionTreeClassifier(max_depth=1,
  random_state=0)` on labeled **development** anomaly scores. This is a scalar
  application decision boundary, not a newly trained vision/world model or a
  probability calibration. Record all samples, actual scores, source/model/
  preprocessing versions and fitted tree. Never hardcode a number chosen to
  pass the known failure. A split that does not separate the development cases
  must be reported, not repaired by inventing a result.
- Positive correspondence alone cannot confirm. Every geometrically linked,
  descriptor-supported candidate must carry an executed appearance assessment.
  An appearance rejection in a spatial cluster vetoes its confirmation, even
  if other views match. Missing/invalid assessment is terminal FAIL. Require
  two distinct observed views, reference coverage and spatial consistency as
  before. Multiple supported instances remain inconclusive.
- Scores and high-distance maps mean appearance unsupported by the supplied
  references. They do not prove that a region is an object defect, establish
  physical identity, observed absence or current room state. Novel true views,
  background or occlusion may lead to inconclusive results.

## Process and evidence boundaries

A required isolated `.venv-anomaly` subprocess owns original inference and the
fitted classifier. One request in flight, no frame queue, bounded deadline,
cancellation and process cleanup. Start/verify it before motion and call it only
after acknowledged stationary disarm. It receives reference/crop images, not
renderer identity/placement/pose labels. Record exact crop/reference hashes,
raw maps, upstream function hash, checkpoint and classifier-artifact hash.
Model/source/environment/artifact failures terminate the capability; no alternate
model, old verifier, PCA path, operator assertion or canned result is permitted.

New search profile/payload **v3** preserves original v2 historical semantics.
App/API/export disclose AnomalyDINO and the project-specific fitted decision
and multi-view aggregation. Qualification binds source, environment and fitted
artifact identity. Existing certificates cannot qualify the changed method.

## Acceptance

1. Execute original upstream scoring on genuine recorded app crops; freeze and
   disclose the development fit. Known failed cases stay development/regression.
2. Replay the original false confirmation through the new required path and
   verify rejection; replay a true target and verify retained positive support.
   Test missing assessment/model/source/calibration explicitly.
3. Freeze fresh simulator cases before execution, paired positives/negatives,
   look-alikes, one gallery, one view, ambiguous references and duplicate objects.
   Do not change thresholds/models after inspecting held-out results.
4. Run actual app enrollment → bounded simulator motion → real model views →
   verdict. No false confirmations and required positive cases must pass; count
   every error, abstention and intervention. Keep memory publication blocked
   until the frozen evaluation passes.
5. Exercise qualified sighting publication and Library/Room history only after
   that gate. Run offline/browser/build checks and capture actual figures.
   No GPU, paid API or live robot is required by this test profile. Real-room
   and physical PuppyPi acceptance remain separate and unverified.

Current implementation and acceptance: **IN PROGRESS**, not a completion claim.
