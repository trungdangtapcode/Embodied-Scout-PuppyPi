# FATAL / CRITICAL / LETHAL PROBLEM: capability integrity and missing research integration

Date: 2026-10-31 (Asia/Tokyo). Audited code revision: `1ede829`.
Status: **OPEN — FAIL against the promised research-backed capabilities.**
Severity: **FATAL / CRITICAL / LETHAL**, explicitly requested by the user as the
highest-priority project review. These labels describe a delivery and reporting
failure; they do not assert that a physical injury or fatality occurred.

**User rating: 0/10. User verdict (translated into English): "like shit".**
Recorded on 2026-10-31 after the follow-up audit of paper-repository reuse for
tracking, path finding and memory. This is the user's assessment of delivery
against the requested research integration, not an automated benchmark score.

## Incident and impact

The user requested application features built by reusing existing research code,
not just academic proposals. The assistant produced substantial research documents,
an operator app and deterministic baselines, then described progress in terms that
led the user to believe the research-backed recognition and room-understanding
pipeline had been integrated. Repeated clarification exposed that the actual
Room memory flow uses handcrafted image features, human-confirmed identities and
regions, SQLite retrieval and manually specified query rules. No Mind Palace or
DynaMem implementation runs in that supported flow.

The reporting failure extends beyond Room memory. MuJoCo animation, simulator
viewpoint placement, logical return-to-HOME, annotation-based inspection and
heuristic verification cannot be presented as learned locomotion, autonomous
navigation, successful physical return, visual absence detection or calibrated
confidence. This mismatch can cause inaccurate academic progress reports,
invalid acceptance decisions and wasted integration effort. The assistant is
responsible for the overstated delivery; the user's expectations were explicit.

The user subsequently set binding acceptance rules: no hardcoded substitution,
no fallback, and FAIL if the promised implementation does not run. The final
clarification permits a heuristic solution when it was explicitly described as
heuristic from the outset. A claim of AI/model inference requires actual model
execution; a claim of using a research repository requires using its implementation.

## Code-backed capability audit

All entries below describe static code inspection and prior labeled test evidence,
not fresh model inference or physical validation during this review.

| Area | Actual implementation and evidence pointer | Claim that must not be made |
| --- | --- | --- |
| Operator app, library and evidence | [API](../../teach_and_find/mobile/api.py), [library](../../teach_and_find/library.py), [storage](../../teach_and_find/storage.py) and browser UI implement real local workflows and persistence | A working app/database proves autonomous perception or integrated research |
| Object proposals | [CandidateProposalGenerator.propose](../../teach_and_find/perception/proposals.py) uses color saliency, thresholds, morphology and contours | A pretrained object detector or semantic segmentation model runs here |
| Object matching / Teach and Find | [SpatialAppearanceEncoder](../../teach_and_find/perception/encoder.py) computes handcrafted color/gradient descriptors; [ObjectMemoryBank](../../teach_and_find/perception/memory.py) matches stored prototypes | A trained few-shot model or a pretrained vision backbone was evaluated in the default demo |
| Optional backbone | `TorchHubBackboneEncoder` exists, but default configuration and inherited evaluation explicitly select the handcrafted encoder | An adapter's existence establishes model loading, inference, performance or app integration |
| Multi-view verification | [VerificationSession](../../teach_and_find/verification.py) uses fixed candidate angles, weighted scores, thresholds and a sigmoid accumulator | Calibrated posterior probabilities or a verified reproduction of a cited research algorithm |
| Search planning | [ActiveSearchPlanner](../../teach_and_find/planner.py) scores a manually constructed station graph; shortest paths use Dijkstra and configured weights | Learned navigation, automatic mapping, measured information gain or a trained search policy |
| AprilTag pose | [AprilTagPoseEstimator](../../teach_and_find/apriltag_pose.py) executes OpenCV tag detection and IPPE-square pose estimation from image corners | All vision is fabricated, or tag pose alone proves obstacle avoidance/whole-room understanding; physical accuracy is unverified |
| Inspection | [InspectionService](../../teach_and_find/inspection.py) evaluates supplied assertions; [demo_assistant.py](../../scripts/demo_assistant.py) injects presence, absence and visibility fixtures and checks an expected summary | The camera autonomously detects missing objects, placement or occlusion |
| Room memory | [RoomService](../../teach_and_find/room.py) queries recorded assertions with bounded temporal rules; [SceneService](../../teach_and_find/scene.py) saves suggestions only after explicit human identity/region confirmation | Mind Palace, DynaMem, an automatic scene graph or a learned world model is integrated |
| Synthetic viewpoint acquisition | [run_closed_loop_episode](../../teach_and_find/sim/evaluator.py) uses simulator-known station/object positions to place rendered cameras at inspection views | The navigation stack independently finds and physically reaches those views; this is an oracle-assisted viewpoint shortcut |
| Return HOME | [FailureAwareMissionController._complete_confirmed_target](../../teach_and_find/mission.py) adds graph distance, assigns `current_node_id = HOME`, and writes `Returned safely to HOME` | The robot executed or measured a successful return; the current success log is misleading outside the logical harness |
| MuJoCo gait | [set_puppypi_pose_and_gait](../../teach_and_find/sim/mujoco_arena.py) directly assigns `qpos` using sinusoidal leg motion and calls `mj_forward` | Closed-loop physics locomotion, a custom learned gait controller, RL training or sim-to-real success |
| Manual control and stop | [OperatorRuntime](../../teach_and_find/mobile/runtime.py), [devices](../../teach_and_find/mobile/devices.py) and [relay](../../scripts/puppypi_edge_relay.py) implement leases, bounded commands, watchdog and transports; default device is synthetic | Loopback/software stop evidence establishes physical stopping time, real execution or autonomous control |
| Phone Observer, patrol and active perception | [Roadmap](../06-feature-roadmap.md) retains planned external-phone capture, calibration/fusion, patrol and view/question selection | A phone PWA is already a third-person camera, or proposal text is implemented patrol/active vision |

This audit does not classify every algorithm as fake. AprilTag geometry, image
feature computation, matching, planning, storage and control logic execute actual
code. The failure is representing their limited scope, scripted inputs or
unimplemented extensions as the more capable system the user requested.

## Follow-up audit: paper repositories were not integrated

The user explicitly clarified that the question concerned implementations from
tracking, path-finding/navigation and memory papers. Generic libraries, CAD assets
and an app framework do not fulfill that request. The inspected supported runtime
does not execute a paper-repository implementation for any of these three areas.

| Requested area | Actual state | Acceptance |
| --- | --- | --- |
| Tracking | No video object tracker with cross-frame identity association is integrated; independent crop matching is not a tracking pipeline | FAIL / not delivered |
| Path finding / navigation | Project-owned Dijkstra and heuristic station scoring operate on a manually declared graph; VLFM and ViNT/NoMaD implementations are not integrated | FAIL against the requested research-repository integration |
| Memory | Project-owned prototype storage, sighting counters, SQLite history and query rules; ReMEmbR, DynaMem and Mind Palace implementations are not integrated | FAIL against the requested research-repository integration |
| Active verification | The IEVE-inspired label refers to project-owned scoring/threshold/angle logic; IEVE source is not integrated | FAIL for any claim of IEVE repository reuse |

The original Teach and Find baseline was imported from the existing project
handoff. Its import commit is not evidence of upstream paper-code reuse; no
verified paper-repository provenance was established for that baseline. The
[reuse register](../08-system-evolution.md) is a research/candidate list, not an
inventory of installed or executed integrations. A configurable Torch Hub adapter
does not change the absence of demonstrated upstream model execution.

The user's 0/10 verdict reflects this unmet core requirement and overstated
reporting. Do not raise the score, close this review, or mark the integration
complete because this audit, another proposal, screenshots or baseline tests exist.
Closure requires the actual implementation and execution evidence described below.

## Claims withdrawn or narrowed

- Withdraw any implication that research documents or the Room memory UI deliver
  an integrated Mind Palace/DynaMem pipeline. The current feature is an
  annotation-backed historical evidence browser with heuristic suggestions.
- Withdraw any claim of RL locomotion, a learned world model or pretrained vision
  inference from the audited default demo. No such execution was demonstrated.
- Narrow synthetic Teach and Find results to the handcrafted visual pipeline and
  oracle-assisted viewpoint harness. They do not establish end-to-end autonomy.
- Narrow inspection results to rules evaluated over operator/script assertions.
  The scripted demo summary is a workflow check, not recognition accuracy.
- Narrow HOME, travel and stop results to their actual logical, estimated or
  loopback evidence. Never reuse the current HOME success log as motion evidence.
- Retain verified local app/persistence/reporting capabilities, with their input
  source and human involvement stated. An Integrated software subset is not
  acceptance of a broader autonomous feature.

The existing 58 Python tests, five Chromium scenarios and successful builds are
software evidence. They do not demonstrate model quality, upstream research
integration, navigation feasibility, learned locomotion or physical safety.

## Binding acceptance rules

1. **State the method before implementation.** A declared heuristic is allowed.
   Do not promise AI/research integration and later deliver a heuristic under
   the same claim. Do not silently downgrade any agreed method.
2. **No hardcoded capability substitution.** Do not obtain automatic identity,
   location, absence, navigation or action-success results from canned labels,
   hand-entered facts, simulator truth or scripted animation when those are what
   the claimed algorithm is supposed to infer or execute. Labeled fixtures remain
   valid tests/comparisons only and cannot satisfy autonomous acceptance.
3. **No fallback for the promised execution path.** Missing weights, dependencies,
   input contracts, endpoints or upstream components make that capability FAIL.
   Do not replace them with mock data, a different backend, manual review or a
   heuristic, whether silently or under an ostensibly successful fallback status.
   Robot stop/watchdog behavior must remain independent and functional.
4. **AI claims require actual inference.** Record model identity, weight/version,
   preprocessing, configured device, executed entry point, input/output and run
   evidence. Existing classes, installation and synthetic fixtures are insufficient.
5. **Research-repository claims require actual implementation reuse.** Record
   upstream URL, revision, license, reused components and modifications, then run
   them in the supported product path. Inspiration or an independent
   reimplementation must be named as such and cannot satisfy a repo-reuse claim.
6. **Completion requires an observable chain.** Trace admitted input through the
   promised algorithm/model to persisted evidence and the app result. Label
   operator assertions and simulator truth separately. Test the missing-model or
   missing-dependency failure and expose that failure to the operator.
7. **Validate the claimed scope.** Algorithm accuracy needs labeled evaluation;
   physics control needs closed-loop execution; hardware capability needs measured
   physical evidence. UI tests and screenshots establish none of these by themselves.
8. **No retrospective laundering.** Documentation, renaming, additional tests of
   the same baseline or a replacement proposal cannot turn the missing capability
   into a completed feature. Report FAIL until the promised path runs.

## Remediation and closure evidence

| Priority | Required correction | State / closure evidence |
| --- | --- | --- |
| P0 | Publish this incident, link it from status/roadmap/application docs, and make agents read it | Documented by this change; this is not implementation remediation |
| P0 | Use this audit in all future progress claims, academic messages and demos | Mandatory ongoing requirement; prior messages cannot be retroactively corrected by Git |
| P0 | Correct misleading runtime success/score terminology, especially logical HOME success | OPEN; runtime code is unchanged in this review |
| P1 | Audit and select an actual upstream implementation against PuppyPi inputs, hardware and deployment constraints | OPEN; record revision/license/component reuse and missing requirements before claiming selection works |
| P1 | Run the selected upstream example, then connect its relevant inference/memory implementation to the app | OPEN; retain commands, configuration, actual input/output, provenance and an app-visible result |
| P1 | Expose required-component failures without fallback | OPEN; code and failure-path execution evidence required |
| P1 | Evaluate recognition, identity association and supported temporal answers on labeled inputs, including real images | OPEN; distinguish comparison heuristics, oracle inputs, human labels and held-out evaluation |
| P2 | Remove oracle viewpoint dependence for an autonomous acquisition claim and measure execution/results | OPEN; requires a real executor and independently evaluated localization/control |
| P2 | Demonstrate learned locomotion or physical return only if those remain promised scope | OPEN / not delivered; animation or a state assignment cannot close this item |

The following paragraph records the original review snapshot; the later
component execution is documented in the subsequent-experiment section below.

For context, the [official Mind Palace repository](https://github.com/mind-palace-laeqa/benchmark)
was verified during the preceding source check to contain a reference
implementation and an example notebook, with OpenAI API usage documented in its
README. It has not been installed, executed or integrated here. This link is an
upstream candidate, not evidence that it is compatible, free to run, or already
selected as the working PuppyPi implementation. Do not invoke paid services merely
to make this incident look resolved.

The next concrete implementation step is an upstream source/dependency/input
audit followed by execution of its actual supported example in an isolated
environment, reporting blockers as FAIL. No further claim of integrated AI or
room understanding is justified by this documentation change.

## Review change scope and verification

### 2026-11-01 source-contract review and proposed remediation

[Document 21](../21-mind-palace-integration-fix-proposal.md) records four offline
reproductions against the pinned Mind Palace source: malformed detection/readiness
strings become positive decisions, empty viewpoint selection triggers substitute
selection, and simulated movement can report an unknown requested endpoint.
These are injected-response/metadata probes, not evidence of model accuracy or
physical execution. A separate real Huey SQLite consumer probe verifies basic
queue isolation and one-attempt failure reporting. It does not implement the app
worker. All proposed contracts, persistence and UI changes remain unimplemented;
the incident and the user's 0/10 delivery rating remain unchanged.

### Subsequent upstream experiment; incident remains OPEN

The [execution report](../20-room-memory-upstream-validation.md) adds real source
inspection, isolated dependency installation and two successful one-image
component replays through Mind Palace revision
`b59be261f9508c3a355a8afa0d495eeba0417d68` with actual GPT-4o calls. The user
authorized API use and supplied the key's configuration location. A standalone
reproducer and source/input hashes are retained; there is no local GPU inference.

This establishes component execution only. No upstream path has yet been
integrated into the PuppyPi app; the original benchmark still fails because scene
files are unavailable under the observed Google Drive quota. The tested ReMEmbR
OpenAI initialization also fails, and the initial Mind Palace JSON-fence parse
failure is retained. No missing-stage or app acceptance condition is closed, and
the user's 0/10 delivery rating is unchanged. This evidence does not retrospectively
validate earlier claims. The original review-change scope below remains historical.

This change records the incident and updates repository instructions and current
documentation entry points. It adds no model, changes no runtime behavior and
does not repair the listed implementation gaps. Historical research ledgers,
screenshots and experiment records are preserved with this correction linked
from current status documents. No robot, external model or paid API is invoked.

Documentation verification: run `make check` and record its actual outcome in
the [dated handoff](../handoffs/2026-10-31-handoff.md). Documentation checks do not
change the incident's OPEN / FAIL acceptance status.

## 2026-11-01 implemented recorded-memory slice; incident remains OPEN

The user accepted document 21 and authorized implementation. The
[implementation guide](../22-mind-palace-app.md) and
[execution report](../research/2026-11-01-mind-palace-app/report.md) now establish
an actual app → immutable capture → real Huey worker → pinned Mind Palace →
`gpt-6-luna` → persisted cited-answer path on explicitly synthetic images.
Three paired regression questions yielded two supported visual comparisons and
one insufficient-witness outcome; occlusion, missing image/source/key and active
cancellation exposed their actual states without another backend. The real
upstream example/component evidence in document 20 remains separate.

This closes only the absence of an executed **recorded-memory application path**
for that bounded profile. It does not retrospectively validate the original
claims or close the broader incident. Real-room recognition/association quality,
current scene understanding, learned predictive modeling, active acquisition,
physical navigation/control and RL execution remain unverified or missing.
A direct-all-images baseline was faster and used fewer reported tokens on this
six-image case; no research-performance advantage is established. The full
reference benchmark still lacks its scene data. The user's **0/10** assessment
is preserved; an agent does not award itself a revised score.

## 2026-11-01 follow-up code-integrity audit; broader incident still OPEN

The [fresh source/behavior audit](2026-11-01-code-integrity-audit.md) found and
corrected unsupported-backend/empty-crop substitutes, ROS central-crop teaching,
missing close-view reuse, authored success labels, fabricated angle defaults,
misnamed scores and logical HOME logs. App/API/export disclosures now distinguish
custom Python/OpenCV code, assertions, configured optional models and actual
upstream reuse. Nine Mind Palace entries were traced through the real source
with explicitly offline injected responses; this is not new model inference.
Historical paid model runs remain separate evidence.

The identified reporting/guard defects have software corrections; absent tracking,
learned world modeling, VLA/RL and physical navigation are not repaired by them.
The original acceptance gates remain binding and the user's 0/10 rating is retained.

## Later genuine vision execution; identity-quality gate still FAIL

The [YOLOE application execution](../research/2026-11-01-yoloe-app/report.md)
now records actual author source/checkpoint inference, actual Ultralytics
ByteTrack calls, persisted outputs and browser screenshots on 58 synthetic
renderer frames. Three real worker jobs fail explicitly for unavailable or corrupt
artifacts with null results. This repairs the absence of an executed vision
proposal/association app path for that bounded profile; it does not establish
robust exact identity. Empty-room background and look-alike false candidates
remain. No ground truth, baseline or manual label corrects those outputs.

The [DINOv2 comparison-stage proposal](../25-visual-identity-fix-proposal.md)
has genuine CPU feature-extraction probe evidence but is not integrated. Changing
the pipeline requires the user's agreed revision; do not silently add a threshold
or revise acceptance after these failures. Automatic inspection/current room
state, predictive world modeling, navigation and learned locomotion remain open.
The incident remains OPEN / FAIL and the user's rating remains 0/10.
