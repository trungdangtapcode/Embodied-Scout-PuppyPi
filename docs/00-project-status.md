# PuppyPi capability and evidence status

Status date: 2026-11-01. This is the current entry point for interpreting the
original prototype documents and the expanded R&D roadmap.

## Mandatory critical review: OPEN / FAIL

Read the [FATAL / CRITICAL / LETHAL capability-integrity review](review/2026-10-31-fatal-critical-lethal-capability-integrity.md)
before using any capability claim below. Local app integration is implemented,
but the requested research-backed autonomous perception/room-understanding path
has not been delivered. No pretrained vision inference, upstream room-memory
pipeline, learned world model, or RL locomotion was demonstrated in the audited
default demos. Their absence is a failed acceptance condition for those claims,
not a reason to substitute heuristics, mocks, or manual labels.

Heuristics are acceptable when explicitly proposed as heuristics from the outset.
Claims of AI/model execution require actual inference; claims of integration from
a research repository require that implementation in the supported execution path.
These corrections govern progress reports and the interpretation of Integrated
labels, which describe only the stated local software subset. The incident remains
open until the promised paths run with evidence; adding this review does not fix code.

Subsequent [upstream execution evidence](20-room-memory-upstream-validation.md)
records a genuine Mind Palace + GPT-4o component replay on one public image,
repeated successfully with a committed reproducer. A subsequent user-selected
`gpt-6-luna` replay also passed with an explicit API adapter; all eight calls
returned that model. This is outside the app and
does not change default-demo claims or close the incident. The original benchmark
still fails on missing scene data (download quota); the tested ReMEmbR OpenAI
profile fails initialization. No robot or local GPU inference was used.

The subsequent [Mind Palace fix proposal](21-mind-palace-integration-fix-proposal.md)
reproduces four malformed-input/fallback boundary behaviors offline and verifies
Huey 3.5.3 SQLite queue/consumer mechanics in a separate process. It proposes
validated upstream adapters, durable episodes/jobs and app capture/question flows.
Those application changes remain Planned; no new inference or hardware evidence
is claimed by the proposal, and the critical incident remains OPEN / FAIL.

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

## Integrated mobile operator console

The [field console](13-mobile-console.md) adds a responsive Preact/TypeScript PWA
served by optional FastAPI on the host. Monitor shows camera and connection state;
Control provides bounded hold-to-drive with an exclusive expiring lease; Inspect
records operator assertions against displayed fresh frames and evaluates saved
checklists; Library supports enrollment, rename, archive, and image history.
Reports download as HTML/JSON/image ZIP bundles. The CLI and app share the core
and versioned store. The default robot is an interactive synthetic renderer.
The interface defaults to English, with an explicitly selected Vietnamese locale
stored in the browser. Language changes disarm manual control.

Monitor now also offers **Room memory**: a recorded-region browser, an image-linked
timeline, three bounded historical questions and durable/exportable answer
snapshots. **Analyze a viewpoint** connects the existing foreground proposal and
appearance-matching baseline to the displayed frame. Ranked candidates require
explicit operator confirmation before becoming observations. No proposal does
not mean absence; finite sightings do not certify continuous presence. This
local workflow and its application-first delivery sequence are documented in
[the application plan](19-application-delivery-plan.md). SQLite v4 preserves
existing evidence and adds query/analysis/confirmation records.

Python tests cover leases, replay rejection, stale evidence, transport metadata,
API/storage workflows, and stopping during an in-flight send. Chromium browser
tests cover desktop/phone layouts, upload, evidence capture, report download,
hold/release, blur, stop, reconnect, and static-only offline caching. These are
software integration results; physical phone installation and robot execution
remain unverified. Search missions and third-person phone capture are not wired
into this UI.

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

## Deployment facts from the current code

The [visual deployment map](12-deployment-map.md) maps files to the development
host, Pi ROS environment, and vendor hardware. The current local application
runs in host `.venv-dev`; this repository contains no Dockerfile, Compose stack,
custom C/C++ target, or firmware build. Native OpenCV/NumPy code is called through
Python APIs rather than deployed as a separate project service.

The Pi relay is a ROS 2 prototype (`rclpy`), not a ROS 1 implementation. Its live
dependencies and the installed robot environment remain unverified. The host
connects to the Pi TCP server. The legacy `F` request remains bare JPEG; the new
`M` request carries camera/session identity, sequence, and relay-local frame age.
The host estimates capture UTC conservatively using frame age and round-trip
time; this is not synchronized multi-camera timing. A command ACK does not
measure executed motion. The relay watchdog
is a Python timeout callback publishing zero velocity, not a hardware-verified
stopping-time guarantee. The direct ROS node's timer implements only station
selection and alignment/recovery, not a complete live mission loop.

## Planned expansion

Memory Scout and Inspect and Explain have local persistence/reporting foundations.
Their autonomous robot flows, Look-or-Ask, Body-aware Active Vision,
speech interaction, and learned visual route following remain
planned. Feature-level status and acceptance criteria are recorded in
[the feature roadmap](06-feature-roadmap.md). A planning entry is not an
implemented feature.

The [Room Patrol proposal](16-room-patrol-world-model-proposal.md) adds planned
F38 bounded patrol and F39 temporal room-model queries, extending the same memory,
inspection and phone-observer foundations. It does not add a physical executor,
metric reconstruction or obstacle avoidance to the current application.

The [deep research audit](17-deep-research-active-room-inspection.md) identifies
close prior art for patrol, persistent graphs, active views and fault diagnosis.
It proposes joint scene-change/source-reliability evaluation with asynchronous
robot/phone evidence. This is an unimplemented research hypothesis, not a
demonstrated novelty or capability; F33–F39 statuses remain unchanged.

The [skill-based deep review](18-deep-research-room-intelligence.md) adds 27
primary papers/documentation sources, persisted evidence and claims, and a
readable HTML/PDF report. It prioritizes coverage-aware temporal claims and
prospective robot/phone acquisition over generic joint diagnosis. Periodic gated
temporal monitoring is the required strong baseline. This remains a research
proposal; no new perception, phone or physical-patrol capability is delivered.

The new [Phone Observer track](11-phone-observer-research.md) plans a fixed phone
camera for external robot localization, cross-view evidence, view selection, and
paired replay. It reuses the same store and policies. Robot camera provenance is
now persisted in SQLite v4; external-phone streaming, clock alignment/error
bounds, calibration lifecycle, and cross-view fusion remain planned. The operator
PWA uses the phone as a display/controller, not as this third-person camera.

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

This status page and the numbered 06–21 documents describe current scope. Documents
01–05 and the 2026-10-30 handoff remain historical source material. Statements in
those files about novelty, ROS distribution compatibility, hardware safety,
onboard model runtime, and sensor range need the corresponding implementation
or hardware evidence before reuse as current claims.
