# FATAL / CRITICAL / LETHAL PROBLEM: capability integrity and missing research integration

Date: 2026-10-31 (Asia/Tokyo). Audited code revision: `1ede829`.
Status: **OPEN — FAIL against the promised research-backed capabilities.**
Severity: **FATAL / CRITICAL / LETHAL**, explicitly requested by the user as the
highest-priority project review. These labels describe a delivery and reporting
failure; they do not assert that a physical injury or fatality occurred.

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

This change records the incident and updates repository instructions and current
documentation entry points. It adds no model, changes no runtime behavior and
does not repair the listed implementation gaps. Historical research ledgers,
screenshots and experiment records are preserved with this correction linked
from current status documents. No robot, external model or paid API is invoked.

Documentation verification: run `make check` and record its actual outcome in
the [dated handoff](../handoffs/2026-10-31-handoff.md). Documentation checks do not
change the incident's OPEN / FAIL acceptance status.
