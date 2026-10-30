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

`ObjectMemoryBank` stores prototypes and station hit counts in process memory.
It does not yet provide durable, timestamped episodic memory or memory freshness.
`VerificationSession.confidence` and `MatchResult.calibrated_score` are heuristic
scores; their names do not establish statistical calibration.

## Evidence boundaries

| Evidence | What it supports | What it does not establish |
| --- | --- | --- |
| Unit and loopback tests | Tested software behavior on synthetic inputs and a local TCP connection | Physical walking, collision avoidance, Wi-Fi behavior on the robot |
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

Memory Scout, Look-or-Ask, Inspect and Explain, Body-aware Active Vision, a live
operator interface, speech interaction, and learned visual route following are
planned. Their feature-level status and acceptance criteria are recorded in
[the feature roadmap](06-feature-roadmap.md). A planning entry is not an
implemented feature.

## Hardware assumptions to resolve

- Exact PuppyPi kit, Raspberry Pi board, firmware, and ROS version.
- Available camera motion, IMU stream, and repeatable body pose range.
- Reliable movement primitives, camera calibration, and network latency.
- Whether the environment has a GPU host, depth sensing, microphone, or speaker.

Use bounded indoor routes and station localization for the initial deployment.
AprilTags alone do not provide obstacle avoidance. Keep robot-side stop behavior
independent of model inference, and validate each motion primitive before using
it in a mission. No live hardware capability is marked verified yet.

## Documentation precedence

This status page and the numbered 06–09 plans describe current scope. Documents
01–05 and the 2026-10-30 handoff remain historical source material. Statements in
those files about novelty, ROS distribution compatibility, hardware safety,
onboard model runtime, and sensor range need the corresponding implementation
or hardware evidence before reuse as current claims.
