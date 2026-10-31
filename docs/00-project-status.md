# PuppyPi capability and evidence status

Status date: 2026-10-31. This is the current entry point for interpreting the
original prototype documents and the expanded R&D roadmap.

## Implemented baseline

The Python package implements AprilTag pose estimation, foreground proposals,
multi-view appearance prototypes, distractor matching, station priors, search
planning, a mission state machine, and ROS 2/TCP adapters. Tests cover synthetic
perception, planning, verification, and the loopback relay watchdog.

The default visual encoder is a handcrafted spatial descriptor. A Torch Hub
adapter exists, but the inherited experiment scripts explicitly instantiate the
spatial encoder. Their results do not evaluate DINOv2, DINOv3, or YOLOE.

`ObjectLibrary` now persists object identities, reference crops/prototypes, and
timestamped assertions in a versioned SQLite/evidence store. It can restore the
existing `ObjectMemoryBank` with same-mode station counts. The legacy mission FSM
does not yet write observations to this store automatically.
`VerificationSession.confidence` and `MatchResult.calibrated_score` are heuristic
scores; their names do not establish statistical calibration.

## Integrated local operator workflows

`python -m teach_and_find` supports object enrollment, listing, rename, reference
replacement, archive, candidate ranking, observation recording, history,
last-seen lookup, persistent checklists, and HTML/JSON evidence export. Inspection
rules evaluate recorded presence/absence/placement assertions with freshness,
quality, provenance-mode, and contradiction handling. CLI assertions and quality
inputs are supplied by the operator; autonomous image interpretation is pending.

Run `make demo-assistant` for four synthetic objects and a portable report. It
reopens persisted state and yields one pass, two failures, and one unknown.
The [operator guide](10-operator-workflows.md) records entry points, limitations,
and feature-specific test evidence. No robot is contacted by this workflow.

## Evidence boundaries

| Evidence | What it supports | What it does not establish |
| --- | --- | --- |
| Unit and loopback tests | Tested software behavior on synthetic inputs and a local TCP connection | Physical walking, collision avoidance, Wi-Fi behavior on the robot |
| Persistent library / CLI / report tests | Restart, schema upgrades, image integrity, annotation-driven inspection, provenance separation | Automated absence detection, calibrated uncertainty, autonomous inspection patrol |
| Synthetic image benchmark | Search and verification decisions for the supplied rendered objects | Generalization to real objects or end-to-end physical control |
| MuJoCo images and animation | CAD scene assembly and rendered viewpoints | Closed-loop physics, learned gait control, sim-to-real transfer |
| Driver audit | Constraints inferred from the inspected vendor source | Validation on the user's specific robot/firmware |

The synthetic evaluator places the camera at selected station and object views.
It does not integrate every issued velocity through a physical locomotion model.
Reported travel is a simulation estimate, not measured hardware odometry.
Returning to `HOME` is represented in mission logic; successful physical return
still needs a navigation execution test.

The historical 100% result concerns 40 synthetic trials for the full-system
variant. It is neither a hardware success rate nor a guarantee on new objects.

## Planned expansion

Memory Scout and Inspect and Explain have local persistence/reporting foundations.
Their autonomous robot flows, Look-or-Ask, Body-aware Active Vision, a live
operator interface, speech interaction, and learned visual route following remain
planned. Feature-level status and acceptance criteria are recorded in
[the feature roadmap](06-feature-roadmap.md). A planning entry is not an
implemented feature.

The new [Phone Observer track](11-phone-observer-research.md) plans a fixed phone
camera for external robot localization, cross-view evidence, view selection, and
paired replay. It reuses the same store and policies. Camera/session metadata,
clock alignment, streaming, calibration, and fusion are not implemented yet.

## Hardware assumptions to resolve

- Confirmed by the user: **PuppyPi Standard**, with **more than three months**
  available. Raspberry Pi board, firmware, and ROS version remain unverified.
- Available camera motion, IMU stream, and repeatable body pose range.
- Reliable movement primitives, camera calibration, and network latency.
- Whether the environment has a GPU host, depth sensing, microphone, or speaker.

Use bounded indoor routes and station localization for the initial deployment.
AprilTags alone do not provide obstacle avoidance. Keep robot-side stop behavior
independent of model inference, and validate each motion primitive before using
it in a mission. No live hardware capability is marked verified yet.

## Documentation precedence

This status page and the numbered 06–11 documents describe current scope. Documents
01–05 and the 2026-10-30 handoff remain historical source material. Statements in
those files about novelty, ROS distribution compatibility, hardware safety,
onboard model runtime, and sensor range need the corresponding implementation
or hardware evidence before reuse as current claims.
