# PuppyPi feature roadmap

PuppyPi combines an object-finding assistant, a visual inspection assistant, and
an experimental platform for memory, uncertainty, and active perception. Build
many demonstrable capabilities on shared perception, memory, and motion services.
Each feature must have an observable outcome, a failure outcome, and evidence.
Internal modules and renamed versions of one behavior do not count as separate
completed user features.

## Status and priority

- **Prototype**: implemented in the current library, synthetic harness, or mock
  relay; operator integration and hardware acceptance may still be missing.
- **Planned**: specified here, not implemented.
- **Integrated**: reachable through the supported mission/operator flow with
  automated or recorded replay evidence. No feature has this new milestone yet.
- **Hardware verified**: passes its acceptance scenario on the documented robot
  configuration, with a run manifest and evidence. None is claimed yet.

P0 establishes the real robot baseline. P1 expands visible functionality with
shared infrastructure. P2 adds the main research experiments. P3 contains optional
hardware/model extensions. Priorities are dependencies, not calendar promises.

## Feature inventory

| ID | Feature | Current status | Priority | Demonstration and acceptance evidence | Depends on |
| --- | --- | --- | --- | --- | --- |
| F01 | Teach an object from several views | Prototype: Python API | P0 | Enroll references; find the taught object; reject an empty reference set | — |
| F02 | Search stations for a taught object | Prototype: synthetic harness | P0 | Visit stations and report found or exhausted search within a budget | F01 |
| F03 | Reject look-alike objects through multiple views | Prototype: synthetic harness | P0 | Distinguish a target/decoy pair using a discriminative side view | F01 |
| F04 | Recover station localization after tag loss | Prototype: FSM and synthetic input | P0 | Recover a visible tag or stop/skip after timeout; record outcome | F02 |
| F05 | Request return to HOME after a mission | Prototype: mission logic | P0 | Physically reach HOME or explicitly report return failure | F02, F09 |
| F06 | View the robot camera remotely | Prototype: TCP client | P0 | Display a fresh frame with timestamp; expose stale/disconnected state | — |
| F07 | Operator stop and communication-loss stop | Prototype: relay watchdog only | P0 | Stop in mock tests; measure physical response; provide operator stop | F06 |
| F08 | Inspect mission evidence and replay | Prototype: offline plots/GIFs | P1 | Show ordered observations, rejected candidates, and final outcome | F02, F03 |
| F09 | Execute calibrated routes between stations | Planned | P0 | Repeat each bounded route; measure failures and operator interventions | F06, F07 |
| F10 | Manage a persistent library of taught objects | Planned | P1 | Create, rename, update, list, and remove an object; survive restart | F01 |
| F11 | Inspect where and when an object was last seen | Planned | P1 | Query an object and return its observation time, station, and image | F10 |
| F12 | Find an object after it moves | Planned | P2 | Visit stale location, collect contrary evidence, find new location | F09, F11 |
| F13 | Distinguish an unclear view from observed absence | Planned | P2 | An occluded view preserves uncertainty; a clear negative updates belief | F03, F11 |
| F14 | Inspect an object's location history | Planned | P1 | Show timestamped sightings and corrections with source evidence | F11 |
| F15 | Queue several object-finding requests | Planned | P1 | Process targets in order; preserve memory; expose per-target outcome | F02, F10 |
| F16 | Request a task in natural language | Planned | P1 | Map a bounded request to a validated task; reject unsupported actions | F10 |
| F17 | Clarify an ambiguous target | Planned | P2 | Ask a question grounded in actual candidates; apply answer or timeout | F16, F03 |
| F18 | Choose whether to look again or ask | Planned | P2 | Compare movement/time and user-question counts at matched error rate | F17, F19 |
| F19 | Report uncertainty or abstain from confirmation | Planned | P2 | Target-absent and unresolved cases produce explicit inconclusive results | F03, F13 |
| F20 | Register an inspection checklist and reference views | Planned | P1 | Define visible predicates and inspection stations; persist the checklist | F10, F11 |
| F21 | Check whether expected items are present | Planned | P1 | Detect a missing item; retain unknown when view is obstructed | F09, F20 |
| F22 | Detect visible open/closed state changes | Planned | P2 | Evaluate supported containers under changed angles and illumination | F20, F19 |
| F23 | Detect an item at the wrong station | Planned | P1 | Compare observed placement to a user-defined rule; attach evidence | F11, F20 |
| F24 | Inspect a change again before reporting it | Planned | P2 | Acquire a second useful view; suppress a nuisance lighting change | F21, F22, F23 |
| F25 | Export an inspection report with evidence | Planned | P1 | Export per-check pass/fail/unknown, timestamps, and image references | F20, F08 |
| F26 | Improve observation by changing body pose | Planned | P2 | Use only measured feasible poses; compare to fixed-pose observation | F07, F09 |
| F27 | Wait for a stable frame before recognition | Planned | P2 | Compare sharpness, recognition, and delay with continuous capture | F06, F26 |
| F28 | Operate missions from one interface | Planned | P1 | Teach/search/inspect, live state, evidence, stop, and connection health | F06, F07, F10 |
| F29 | Issue spoken requests and hear results | Planned | P3 | Reuse the validated text task path; handle ASR errors and cancellation | F16, F28 |
| F30 | Teach and replay a route using visual landmarks | Planned | P3 | Evaluate repeatability and interventions on held-out route conditions | F09 |
| F31 | Propose unfamiliar objects from image/text prompts | Planned | P2 | Evaluate pretrained proposals on real crops, including missed objects | F01, F06 |
| F32 | Compare algorithms through repeatable experiments | Prototype: four-way synthetic ablation | P1 | Reproduce paired trials and export metrics with revision/config/seed | F08 |

Statuses describe the current baseline, not promises of physical performance.
Speech can initially use the operator laptop's microphone and speaker. F30 is an
optional navigation study; initial application demos can use validated stations.

## Delivery order

| Milestone | Scope | Exit condition |
| --- | --- | --- |
| M0 Repository and evidence foundation | Reproducible install, baseline code, source attribution, status, contribution rules | Checks/tests/build pass; historical and planned claims are distinguished |
| M1 First real Teach and Find mission | F01–F07 and F09; initial real-object proposal evaluation | Timestamped live video, stop behavior, calibrated station route, real target/decoy trial |
| M2 Broad application demo | F08, F10, F11, F14–F16, F20, F21, F23, F25, F28 | One operator flow demonstrates object library, search, history, and checklist reports |
| M3 Memory and decision research | F12, F13, F17–F19, F24, F31, expanded F32 | Held-out experiments isolate memory freshness, observation quality, and action selection |
| M4 Embodied vision and interaction extensions | F22, F26, F27, F29, F30 | Each extension passes its own physical prerequisite and ablation |

M2 deliberately shares an evidence store and task model across applications.
M3 and M4 extend that system rather than creating separate demo-only controllers.
Adjust scope after confirming the deadline, grading rubric, kit, team size, and
available sensors. These details are not yet established.

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

Use live failures and recovery as part of acceptance. A prerecorded successful
trajectory alone does not demonstrate autonomy.

## Feature completion record

For each promoted feature, record its ID, implementation entry point, test or
replay, operator steps, physical prerequisites, failure behavior, and evidence
manifest. Track the status independently for software and hardware. Do not count
an unimplemented screen, a placeholder service, or a roadmap row as delivered.
