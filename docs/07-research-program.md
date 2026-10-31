# PuppyPi research program

The application roadmap supports five research tracks. Each track has a
testable hypothesis, reusable prior work, and controlled baselines. Combining
existing models or deploying on a less expensive robot alone is not evidence of
algorithmic novelty. The proposed contributions remain hypotheses until compared
with the closest work and validated experimentally.

The [deep room-inspection review](17-deep-research-active-room-inspection.md)
updates R1/R3/R5 together: persistent IDs, visibility-gated absence, uncertainty
view selection and active fault diagnosis already have close prior art. Use its
stronger gated/cascade baselines and joint-change/source-fault protocol before
claiming novelty from the simpler hypotheses below. Feature statuses are unchanged.

## R1 Temporal memory and active verification

**Question:** when previous sightings conflict with current perception, how
should the robot allocate observation and search effort?

**Hypothesis:** memory freshness combined with observation quality reduces false
location confirmations and wasted travel relative to static memory or uniform
memory expiration at comparable task success.

Build on [ReMEmbR](https://github.com/NVIDIA-AI-IOT/remembr) for spatio-temporal
retrieval, [DynaMem](https://dynamem.github.io/) for changing-world memory, and
[IEVE](https://github.com/XiaohanLei/IEVE) for switching between exploration and
verification. DynaMem's RGB-D point-cloud memory and Stretch deployment are not a
drop-in implementation for a monocular PuppyPi.

Proposed scope: station/object observations with timestamps, visibility and
quality estimates, competing identities, and source images. Keep old observations
immutable; revise the current belief rather than rewriting historical evidence.
An old sighting should become less informative, not automatically become proof
of absence. An obscured camera view is not a verified negative observation.

**Baselines:** current hit-count prior; last-seen station; fixed time decay;
freshness-aware belief; freshness plus active verification. Hold the detector,
encoder, navigation executor, and search budget fixed.

**Outcomes:** exact-instance success, false confirmation, search time/distance,
revisits, and observations needed to repair an outdated location belief.
Features: F11–F14, F19, F24.

## R2 Looking versus asking under ambiguity

**Question:** when is another visual action more useful than a human question?

**Hypothesis:** joint action selection achieves comparable error rates with fewer
questions and less movement than always-ask, never-ask, or fixed-view policies.

[KnowNo](https://github.com/google-research/google-research/tree/master/language_model_uncertainty)
studies uncertainty-aligned requests for help.
[LEGS-POMDP](https://ivyyyy24381.github.io/LEGS/) models target identity and
location uncertainty using language, gesture, and vision. These are close prior
work, not capabilities newly introduced by this project. The LEGS-POMDP code link
could not be retrieved during the 2026-10-31 review; do not schedule integration
until a usable release is verified.

Proposed actions: observe from a feasible viewpoint, visit another station, ask a
candidate-grounded question, confirm, or abstain. A tractable first policy ranks
expected information gain against measured action time and question cost. Estimate
these terms on held-out calibration episodes and compare to simpler thresholds.
Natural language parsing must not directly issue motor commands.

**Baselines:** never ask; ask whenever more than one candidate remains; fixed
multi-view verification; cost-aware joint choice. Include incorrect/ambiguous
human answers, unanswered questions, and cases no available question can resolve.

**Outcomes:** selection accuracy, question count, human response time, travel,
task duration, and risk versus coverage. Conformal guarantees require their
assumptions; do not transfer them automatically to adaptive, shifted robot data.
Features: F16–F19.

## R3 Question-driven inspection and change verification

**Question:** which observations are necessary to establish a requested state
change while avoiding reports caused by lighting, perspective, or occlusion?

**Hypothesis:** relevance-aware change detection followed by active verification
improves report precision at matched recall relative to one-view comparison or
an unverified VLM judgment.

[Explore until Confident](https://explore-eqa.github.io/) provides a foundation
for exploration and calibrated answering, with
[code](https://github.com/Stanford-ILIAD/explore-eqa).
[DovSG](https://github.com/BJHYZJ/DovSG) studies updating open-vocabulary scene
graphs with RGB-D input.
[Sight Over Site](https://sight-over-site.github.io/) optimizes access to an
observable viewpoint; its original policy uses depth and relative target state.

Start with explicit predicates: an item is present at a station, a supported
container is open/closed, or an observed item violates a location rule. Associate
each finding with a baseline observation, a current observation, and a result of
pass/fail/unknown. Inspect unknowns again only while within the mission budget.

**Baselines:** aligned image difference; frozen visual-feature difference;
single-view VLM answer; repeat-view verification. Use the same reference scenes
and include nuisance-only changes.

**Outcomes:** per-predicate precision/recall/F1, false alarms per completed patrol,
unknown rate, inspection time, revisits, and evidence completeness.
Features: F20–F25.

## R4 Body-aware observation selection

**Question:** under a low camera and walking-induced motion, when should the
robot change its pose, move, or wait for a stable image?

**Hypothesis:** quality-aware selection improves recognition per observation or
per second compared with fixed-pose and fixed-sweep policies.

The [POSE preprint](https://arxiv.org/abs/2609.19460) already studies body pitch
and roll for semantic exploration with omnidirectional camera–LiDAR sensing.
It was listed as under review and planning a future code release when reviewed.
Treat it as related work, not an available PuppyPi controller.

Use the vendor gait controller and a measured library of feasible actions. Do
not assume that an accepted lateral command produces reliable lateral motion or
that CAD meshes supply a validated dynamics model. Log actual tag-derived pose,
or another measured pose estimate, separately from commanded pose. Start with
sharpness/visibility gating before adding learned viewpoint selection.

**Baselines:** continuous capture; stop-and-capture; fixed pose sweep;
quality-aware action choice. Evaluate the same objects and view budgets.

**Outcomes:** instance recognition, useful-view yield, time to confirmation,
blur, missed tags, and physical interventions. Report energy only if measured;
distance is not an energy measurement. Features: F26–F27.

## R5 External-view selection with a phone observer

**Question:** when does consulting a fixed external camera improve object finding
or inspection enough to justify transmission, processing, and synchronization cost?

**Hypothesis:** freshness/visibility-aware view selection reduces travel and false
confirmation relative to ego-only and always-fuse approaches at comparable success.
Combine robot close views with a fixed phone overview; use station hypotheses
before attempting metric 3D object reconstruction.

The [Phone Observer research plan](11-phone-observer-research.md) verifies related
work and reusable components: external-camera robot pose estimation, Ego-Exo4D,
AprilTag/OpenCV, and optional aiortc transport. It specifies geometry, clock
uncertainty, camera provenance, and a schedule for PuppyPi Standard. The current
repository has none of the proposed phone capture/fusion components implemented.

**Baselines:** ego only, exo only, always fuse, fixed quality/freshness gates,
cost-aware selection; use an offline oracle only as a diagnostic reference.
Hold perception versions and task layouts fixed. Report equal-time/action and
equal-processed-frame comparisons, with explicit sensor availability.

**Outcomes:** instance/inspection accuracy, false confirmation, unknown rate,
travel, duration, questions, traffic, stream age, clock uncertainty, and physical
interventions. Ground-truth localization must be independent of the camera being
evaluated. Features: F33–F37, enriching F12/F20–F25 without recounting them.

## Shared experimental protocol

1. Collect enrollment images separately from calibration and evaluation data.
   Split by physical instance, layout, or day; adjacent video frames must not
   cross splits. Evaluate both enrolled identities and unseen distractors.
2. Include target-present, moved, absent, look-alike, occluded, lighting-change,
   tag-dropout, and network-delay conditions. Do not inject real network faults
   during walking before validating stop behavior.
3. Use paired layouts and seeds across methods. Reset memory between independent
   methods; preserve it within explicitly defined lifelong sequences.
4. Begin with a pilot to estimate variance and physical runtime. A planning
   target is 40–60 paired missions per main variant, not a statistical power
   guarantee. Treat the mission or memory sequence as the sampling unit.
5. Report interval estimates, all failures, timeouts, and operator interventions.
   Keep module accuracy separate from complete mission success and return-home
   success. Abstention is not successful identification.
6. Log commit SHA, clean/dirty state, dependency-lock hash, settings, random seed,
   model/checkpoint identifiers, robot firmware, calibration, latency, and links
   to consented evidence. Keep recordings and model weights outside Git.
7. Record both proposed and achieved actions. Separate synthetic perception,
   physics simulation, prerecorded replay, and physical closed-loop results.

[GOAT-Bench](https://mukulkhanna.github.io/goat-bench/) offers multimodal lifelong
navigation protocols. [OpenEQA](https://open-eqa.github.io/) provides embodied
question-answering evaluation context. Reusing their task structure does not make
a small station test an equivalent benchmark or justify comparing raw scores.

## Research deliverables

Each track should produce a question and related-work comparison, a reproducible
baseline, one clearly isolated proposed method, an ablation, failure analysis,
and a demo tied to measured behavior. For the confirmed Standard kit and horizon
longer than three months, prioritize R1 and R5 as the main experimental story.
Add R2/R3 through shared application services, and R4 after physical motion
characterization. Do not promise five independently novel algorithms merely
because there are five research tracks.
Publication readiness depends on evidence and comparison, not the feature count.
