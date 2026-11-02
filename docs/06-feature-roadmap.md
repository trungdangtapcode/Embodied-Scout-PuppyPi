# PuppyPi feature roadmap

PuppyPi combines an object-finding assistant, a visual inspection assistant, and
an experimental platform for memory, uncertainty, and active perception. Build
many demonstrable capabilities on shared perception, memory, and motion services.
Each feature must have an observable outcome, a failure outcome, and evidence.
Internal modules and renamed versions of one behavior do not count as separate
completed user features.

Mandatory acceptance correction: read the [OPEN FATAL / CRITICAL / LETHAL review](review/2026-10-31-fatal-critical-lethal-capability-integrity.md).
Existing Integrated labels cover their explicitly bounded local software flows,
not delivery of promised autonomous AI or upstream research pipelines. A required
path that cannot run is FAIL, with no fallback. Heuristics may be delivered only
when declared as the intended method from the outset; a research-repository claim
requires actual reuse and execution of that implementation.

## Status and priority

- **Prototype**: implemented in the current library, synthetic harness, or mock
  relay; operator integration and hardware acceptance may still be missing.
- **Planned**: specified here, not implemented.
- **Integrated**: reachable through the supported mission/operator flow with
  automated or recorded replay evidence. Local CLI integration does not imply
  autonomous perception, mission integration, or physical verification.
- **Hardware verified**: passes its acceptance scenario on the documented robot
  configuration, with a run manifest and evidence. None is claimed yet.

P0 establishes the real robot baseline. P1 expands visible functionality with
shared infrastructure. P2 adds the main research experiments. P3 contains optional
hardware/model extensions. Priorities are dependencies, not calendar promises.

## Feature inventory

| ID | Feature | Current status | Priority | Demonstration and acceptance evidence | Depends on |
| --- | --- | --- | --- | --- | --- |
| F01 | Teach an object from several views | Integrated: persistent CLI enrollment and candidate matching | P0 | Enroll references; find the taught object; reject an empty reference set | — |
| F02 | Search stations for a taught object | Legacy heuristic retained; new original-model/known-map simulator app path executed, complete identity acceptance FAIL | P0 | [Actual motion/model evidence and failures](research/2026-11-02-complete-search/report.md); verified automatic memory still blocked | F01 |
| F03 | Reject look-alike objects through multiple views | FAIL: actual DINOv2/DISK/LightGlue readout falsely confirms a same-front/different-side unknown; no IEVE reuse | P0 | [Illustrated counterexample](review/2026-11-02-yoloe-identity-gate-case.md); [additional-verifier research plan](30-appearance-contradiction-research-plan.md) | F01 |
| F04 | Recover station localization after tag loss | Prototype: FSM and synthetic input | P0 | Recover a visible tag or stop/skip after timeout; record outcome | F02 |
| F05 | Request return to HOME after a mission | FAIL for physical return; logical graph bookkeeping only | P0 | Physically reach HOME or explicitly report return failure | F02, F09 |
| F06 | View the robot camera remotely | Integrated: browser camera, v2 metadata adapter; hardware pending | P0 | Synthetic browser and loopback tests display frame identity/age and disconnected state; verify real camera clock next | — |
| F07 | Operator stop and communication-loss stop | Integrated: UI stop, expiring lease, relay watchdog; hardware pending | P0 | Hold/release, blur, reconnect, stale/replayed commands, in-flight stop tests; measure physical stop next | F06 |
| F08 | Inspect mission evidence and replay | Prototype: app observation timeline and saved answers integrated; full action/run replay pending | P1 | Show ordered observations, rejected candidates, and final outcome | F02, F03 |
| F09 | Execute calibrated routes between stations | Prototype: original PythonRobotics plus observed AprilTag geometry executed in kinematic simulator; physical routes unverified | P0 | [Actual trajectory/pose evidence](research/2026-11-02-complete-search/report.md); no oracle pose input, no physical gait claim | F06, F07 |
| F10 | Manage a persistent library of taught objects | Integrated: CLI, archive preserves evidence | P1 | Create, rename, update, list, and remove an object; survive restart | F01 |
| F11 | Inspect where and when an object was last seen | Integrated: historical-sighting lookup | P1 | Query an object and return its observation time, station, and image | F10 |
| F12 | Find an object after it moves | Planned | P2 | Visit stale location, collect contrary evidence, find new location | F09, F11 |
| F13 | Distinguish an unclear view from observed absence | Prototype: operator-supplied visibility gate | P2 | An occluded view preserves uncertainty; a clear negative updates belief | F03, F11 |
| F14 | Inspect an object's location history | Integrated: ordered assertion/evidence history | P1 | Show timestamped sightings and subsequent assertions with source evidence | F11 |
| F15 | Queue several object-finding requests | Planned | P1 | Process targets in order; preserve memory; expose per-target outcome | F02, F10 |
| F16 | Request a task in natural language | Planned | P1 | Map a bounded request to a validated task; reject unsupported actions | F10 |
| F17 | Clarify an ambiguous target | Planned | P2 | Ask a question grounded in actual candidates; apply answer or timeout | F16, F03 |
| F18 | Choose whether to look again or ask | Planned | P2 | Compare movement/time and user-question counts at matched error rate | F17, F19 |
| F19 | Report uncertainty or abstain from confirmation | Planned | P2 | Target-absent and unresolved cases produce explicit inconclusive results | F03, F13 |
| F20 | Register an inspection checklist and reference views | Integrated: presence/placement rules and enrollment snapshots | P1 | Define visible predicates and inspection stations; persist the checklist | F10, F11 |
| F21 | Check whether expected items are present | Prototype: recorded-assertion rules, no autonomous detection | P1 | Detect a missing item; retain unknown when view is obstructed | F09, F20 |
| F22 | Detect visible open/closed state changes | Planned | P2 | Evaluate supported containers under changed angles and illumination | F20, F19 |
| F23 | Detect an item at the wrong station | Prototype: recorded-assertion rules | P1 | Compare observed placement to a user-defined rule; attach evidence | F11, F20 |
| F24 | Inspect a change again before reporting it | Planned | P2 | Acquire a second useful view; suppress a nuisance lighting change | F21, F22, F23 |
| F25 | Export an inspection report with evidence | Integrated: portable HTML/JSON and PNG evidence | P1 | Export per-check pass/fail/unknown, timestamps, and image references | F20, F08 |
| F26 | Improve observation by changing body pose | Planned | P2 | Use only measured feasible poses; compare to fixed-pose observation | F07, F09 |
| F27 | Wait for a stable frame before recognition | Planned | P2 | Compare sharpness, recognition, and delay with continuous capture | F06, F26 |
| F28 | Operate missions from one interface | Prototype: mobile teach/manual control/inspect integrated; search pending | P1 | Browser workflows cover library, recorded-evidence inspection, camera, stop and health; autonomous search UI remains pending | F06, F07, F10 |
| F29 | Issue spoken requests and hear results | Planned | P3 | Reuse the validated text task path; handle ASR errors and cancellation | F16, F28 |
| F30 | Teach and replay a route using visual landmarks | Planned | P3 | Evaluate repeatability and interventions on held-out route conditions | F09 |
| F31 | Propose unfamiliar objects from image/text prompts | Integrated visual-prompt execution subset on rendered input; text prompts and reliable identity remain pending | P2 | [Combined app execution](research/2026-11-01-dual-vision-app/report.md): 103 rendered frames, actual YOLOE + DINOv2 + custom reference rule + ByteTrack, retained raw/rejected candidates and eight required-component failures; exact identity and real-room quality remain open | F01, F06 |
| F32 | Compare algorithms through repeatable experiments | Prototype: heuristic/oracle baseline plus paired raw-YOLOE versus DINOv2 reference-policy evaluation on rendered fixtures; real-room benchmark pending | P1 | Reproduce paired trials and export metrics with revision/config/seed | F08 |
| F33 | Connect a phone as a third-person camera | Planned | P1 | View both sources with capture time, frame age, and disconnect state | F06, F28 |
| F34 | Show externally measured robot position | Planned | P1 | Calibrate phone/world/robot geometry; measure pose error; reject lost or invalid calibration | F33 |
| F35 | Confirm objects and inspection findings across cameras | Planned | P2 | Associate exact instance/station evidence; conflicting or stale views cannot confirm | F11, F20, F33, F34 |
| F36 | Select a robot view, phone view, movement, or question | Planned | P2 | Compare accuracy, time, travel, and questions with equal-budget baselines | F18, F35 |
| F37 | Replay synchronized robot and phone observations | Planned | P1 | Export paired timelines, evidence, clock uncertainty, missing frames and calibration IDs | F08, F33 |
| F38 | Run and resume a bounded inspection patrol | Planned | P1 | Visit verified stations, inspect, pause/take over/resume with revalidation, report incomplete checks and measured HOME outcome | F07, F09, F20, F28 |
| F39 | Inspect and query a temporal room model | Integrated recorded-memory subset: actual Mind Palace + Luna capture/question jobs; automatic current scene state pending | P1 | [App execution](22-mind-palace-app.md): three synthetic episodes/two regions, cited answers, missing/covered evidence abstention, cancellation/source failure; real-room quality, geometry and active execution remain open | F06, F10, F11 |
| F40 | Select a camera target and track future frames | Integrated selection/preview/tracking subset; full feature unfinished, 5 FPS gate FAIL | P1 | [v2 actual app execution](research/2026-11-02-tracking-freshness/report.md): original SAM/Cutie, 292 observations/120 s, latest pending peak 1 under overload, about 2.41 callback FPS; paired sampling outputs differ, quality unverified. [Original FIFO failures](research/2026-11-02-stream-app/report.md) preserved. Find-again/recovery/full export and physical following unfinished | F06, F07, F31 |

Statuses describe the current baseline, not promises of physical performance.
The [Room Patrol proposal](16-room-patrol-world-model-proposal.md) specifies
F38/F39 and their geometry, perception, execution and research prerequisites.
The [deep prior-art audit](17-deep-research-active-room-inspection.md) sharpens
their R1/R3/R5 evaluation: compare joint change/source diagnosis against strong
visibility gates and passive/active diagnosis cascades. These remain plans.
The [subsequent deep review](18-deep-research-room-intelligence.md) makes
coverage-aware temporal queries and prospective acquisition the main experiment,
with periodic gated monitoring and evidence-relative support labels. It does not
add feature entries or change delivery status.
The [application delivery plan](19-application-delivery-plan.md) records the
subsequent implementation: local Room memory, temporal query snapshots, frame
suggestions and explicit operator confirmation. F39 now has an integrated subset,
not autonomous room understanding or a physical verification claim.
The [next-feature research proposal](15-next-feature-research.md) prioritizes
replay, automatic perception, memory repair and selective external views using
verified upstream entry points. Its proposed capabilities do not change the
implementation statuses above.
Speech can initially use the operator laptop's microphone and speaker. F30 is an
optional navigation study; initial application demos can use validated stations.
The [Phone Observer plan](11-phone-observer-research.md) specifies F33–F37 and
related work. Begin with one fixed phone; a handheld observer needs per-frame
camera localization. F34 supplies pose, not general obstacle avoidance.

## Delivery order

| Milestone | Scope | Exit condition |
| --- | --- | --- |
| M0 Repository and evidence foundation | Reproducible install, baseline code, source attribution, status, contribution rules | Checks/tests/build pass; historical and planned claims are distinguished |
| M1 First real Teach and Find mission | F01–F07 and F09; initial real-object proposal evaluation | Timestamped live video, stop behavior, calibrated station route, real target/decoy trial |
| M2 Broad application demo | F08, F10, F11, F14–F16, F20, F21, F23, F25, F28 | One operator flow demonstrates object library, search, history, and checklist reports |
| M3 Memory and decision research | F12, F13, F17–F19, F24, F31, expanded F32 | Held-out experiments isolate memory freshness, observation quality, and action selection |
| M4 Embodied vision and interaction extensions | F22, F26, F27, F29, F30 | Each extension passes its own physical prerequisite and ablation |
| M5 External viewpoint, developed alongside M2–M3 | F33–F37; shared memory and inspection | Calibrated paired views, dropout/clock tests, and controlled ego/exo/fusion comparisons |

M2 deliberately shares an evidence store and task model across applications.
M3 and M4 extend that system rather than creating separate demo-only controllers.
The user confirmed PuppyPi Standard and a horizon longer than three months on
2026-10-31. Exact grading weights, team size, board/firmware, and available host
compute/sensors remain open. M2 persistence and report export are now usable
locally; M1 physical acceptance remains pending.
Use the [adjustable 16-week schedule](11-phone-observer-research.md) to allocate
time to R1 temporal memory and R5 external-view selection, with the other tracks
providing application breadth and optional research extensions.

## Demonstration scenarios

1. **Teach and distinguish:** teach a pouch, place a similar pouch first, show
   rejection and correct identification with reference/candidate crops.
2. **Remember and relocate:** move the known pouch; show the old observation,
   new contradictory evidence, updated search, and new confirmed location.
3. **Resolve ambiguity:** provide an underspecified request; show the selected
   clarification or view and why the subsequent outcome changed.
4. **Inspect a workspace:** register expected items and visible states; remove
   an item and open a container; inspect and export evidence-backed findings.
5. **Recover and abstain:** interrupt a tag observation or remove the target;
   show recovery, bounded search, and an honest inconclusive result.
6. **Observe with the body:** compare a fixed view to a feasible changed pose,
   with measured observation quality and recognition outcomes.
7. **Consult the phone observer:** move an item outside the robot camera's view;
   use a timestamped phone hint, then verify identity from the robot. Disconnect
   the phone or move its stand and show the resulting uncertainty explicitly.

Use live failures and recovery as part of acceptance. A prerecorded successful
trajectory alone does not demonstrate autonomy.

## Feature completion record

For each promoted feature, record its ID, implementation entry point, test or
replay, operator steps, physical prerequisites, failure behavior, and evidence
manifest. Track the status independently for software and hardware. Do not count
an unimplemented screen, a placeholder service, or a roadmap row as delivered.

The [operator workflow evidence table](10-operator-workflows.md) records the
implemented F01/F10/F11/F14/F20/F25 CLI slice and prototype F13/F21/F23 rule engine.
Tests cover restart, incompatible embeddings, stale and contradictory evidence,
cleared locations, and portable report export. Assertions in this release are
operator annotations or synthetic fixtures; none establishes autonomous inspection.
