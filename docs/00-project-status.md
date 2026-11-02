# PuppyPi capability and evidence status

Status date: 2026-11-02. This is the current entry point for interpreting the
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
The user subsequently accepted that design. The [recorded-memory app integration](22-mind-palace-app.md)
now executes the actual pinned Mind Palace source with `gpt-6-luna` through a
separate Huey worker. The [app execution report](research/2026-11-01-mind-palace-app/report.md)
records real UI capture, three synthetic episodes/two regions, persisted answers,
validated image citations, cancellation/source-loss/occlusion and a paired baseline.
Both comparison questions answered; the missing-witness question was inconclusive.
The tiny direct-all-images baseline was faster/cheaper in reported tokens; no
research superiority, held-out real-room quality or physical capability is claimed.
The broader incident remains OPEN / FAIL and the user's delivery rating is unchanged.

## Current code-integrity follow-up

The [2026-11-01 audit](review/2026-11-01-code-integrity-audit.md) found additional
silent substitutes, authored success labels and misleading score/return semantics.
Corrections reject unsupported backends/empty evidence, remove central/overview
crop substitution, preserve unknown angles and distinguish logical HOME from
measured motion. The app now exposes an authenticated method/source inventory
and explicitly labels custom Python/OpenCV heuristics, human/script assertions
and actual optional Mind Palace reuse. New storyboards are permanently labeled;
historical artifacts are preserved with corrections. This does not deliver the
missing research models or close the original incident.

## Implemented baseline

### Current station-search completion attempt: FAIL

The [complete-search contract](29-complete-teach-search-memory.md) now has a new
app/worker path: enrolled images → continuous bounded kinematic simulator motion
using actual AprilTag pixels and original PythonRobotics → actual YOLOE/DINOv2/
ByteTrack/DISK/LightGlue → stored per-view evidence. The user explicitly approved
YOLOE as region proposal, DINOv2 as gallery candidate identity and LightGlue as
local correspondence. Original vision v2 semantics remain preserved.

The [illustrated case review](review/2026-11-02-yoloe-identity-gate-case.md) shows
why the old class-agreement veto rejected a useful target proposal, and a second
case where the revised rule still falsely confirmed an unknown object with the
same front and different sides. The frozen 13-case run has six control failures
and that false confirmation. Per-segment acknowledged disarm fixes are separately
regression-tested; they do not repair identity quality. See the
[execution report](research/2026-11-02-complete-search/report.md).

**Automatic verified memory remains blocked.** The model-sighting/history code
exists behind a closed quality gate; a successful model readout is not delivered
end-to-end verified memory. The user approved [additional contradiction-verifier
research](30-appearance-contradiction-research-plan.md), with concrete method
approval required before integration. No new physical/Pi/real-room/world-model
capability, quality certification or closure of the critical incident is claimed.

The subsequent [executed identity correction](research/2026-11-02-identity-fix/report.md)
requires original AnomalyDINO scoring and an explicitly development-fitted sklearn
scalar gate. It rejects the preserved false confirmation and retains a positive
replay. The first 13-case batch passes; a repeat with loaded-weight verification
is **11/13, FAIL**. One remaining positive fails the single-homography geometric
support rule; a native fundamental-matrix revision is proposed, not integrated,
pending user approval. A separate camera-cadence defect is fixed and three
concurrent same-case model runs complete four views without stale-camera failure.
These regressions do not certify the complete feature. Automatic sightings remain
zero, publication remains blocked, and real-room/hardware validation is absent.

### Executed visual-prompt and descriptor-comparison subsets

The [YOLOE app profile](24-yoloe-vision.md) now invokes the pinned author source,
SAVPE checkpoint and the Ultralytics ByteTrack implementation in a separate CPU
worker. The [actual execution report](research/2026-11-01-yoloe-app/report.md)
records Library enrollment and camera-window inference through the browser on
58 renderer frames, persisted masks/boxes/crops/associations, actual upstream
call counts, desktop/phone screenshots and three artifact-failure jobs with null
results. No GPU, paid API, Pi or physical robot was used in this new experiment.

Execution is integrated; exact-identity quality is **FAIL / unverified**. Moving-
object precision/recall was 59.3%/97.2% in the tiny development fixture; empty-room
and decoy false positives remain, and changed-view recall was 72.2%. Do not count
model execution as automatic inspection, learned room/world modeling, navigation
or RL. F03 and the broader critical incident remain unpromoted. The separate
[DINOv2 comparison proposal](25-visual-identity-fix-proposal.md) has genuine CPU
probe evidence and was subsequently accepted and integrated as described below.

The subsequently accepted **combined YOLOE + DINOv2 + custom cosine/margin +
ByteTrack profile** now has [actual app evidence](research/2026-11-01-dual-vision-app/report.md):
103 rendered frames across nine conditions, genuine source/checkpoint execution
for both models, raw/rejected proposals, reference-image comparisons and eight
explicit required-component/profile/cache failures. New jobs require explicit
version 2; historic profiles are not upgraded implicitly. The worker remains CPU
only. 106 Python and eight Chromium tests plus check/frontend/package builds pass.

In the paired synthetic moving scene, candidate precision rises to 100% while
recall falls from 32/33 to 25/33 under the declared custom rule. Novel-angle recall
is only 15/36, and an unknown object with identical visible faces produces 11
false supported candidates. These development/limited condition-split results do
not establish calibrated rejection, verified exact identity or real-room quality.
The app retains candidate status, does not write verified sightings and does not
claim absence, navigation or a learned predictive world model. The critical
incident remains OPEN / FAIL; this is executed model reuse, not full-goal closure.

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
inputs are supplied by the operator; automatic checklist predicates from images remain pending.
The separate combined-model candidate profile above does not write asserted facts.

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

The [interactive target-tracking design](26-interactive-target-tracking.md), dated
2026-11-02, adds planned F40: select a camera object with a point/box, preview its
actual SAM 2.1 mask, then propagate it on future frames through original Cutie.
Ten repositories were source-inspected; the proposed new models were not installed
or executed and no new app interaction was integrated. Design figures are authored
proposals. CPU live throughput and automatic identity recovery remain unverified;
the current recorded-window profile and its failed identity gate are unchanged.

A later [actual tracking-component probe](research/2026-11-02-tracking-execution/report.md)
now executes SAM 2.1 tiny and original Cutie base-mega on CPU over 12 synthetic
frames. With eight threads, the recorded mean Cutie step was 0.247 s (4.05
compute-step FPS); the separate CUDA trial failed on insufficient available VRAM.
The earlier source-audit-only statements describe the planning stage. No phone
target selection, live session or quality gate is delivered by this CLI probe.

A subsequent [full app execution](research/2026-11-02-stream-app/report.md) integrates
actual frozen-image SAM preview and future-frame Cutie tracking in Monitor.
Two requested-5-Hz sessions fail from accumulated lag; camera callbacks remain
about 3.9 FPS. Concurrent real vision, Mind Palace capture and QA complete using
8 of 15 authorized API attempts. A separate explicit 3 Hz/box-prompt diagnostic
processes 123 observations over one minute at about 2 callback FPS, then stops.
These are authored-render inputs and Chromium mobile/network emulation, not a
physical phone or robot. The [operating guide](27-live-tracking-app.md) lists
missing Find-again/recovery, export and quality work. The full F40 feature,
5 FPS release gate and critical incident remain unfinished/FAIL.

The user subsequently required a scheduling redesign rather than treating overload
as a hardware-only issue. The [v2 scheduling contract](28-live-stream-scheduling.md)
now uses a latest-value mailbox, separate bootstrap/live inbox policies and
observable replacement counts. [Actual correction evidence](research/2026-11-02-tracking-freshness/report.md)
records 292 observations over 120 seconds with one concurrent real vision job,
peak live pending 1 and no catch-up failure. Mask callbacks are about 2.41 FPS;
quality, physical tests and the full 5 FPS/five-minute gate remain unpassed.
The [critical scheduling review](review/2026-11-02-live-stream-overload.md) and
AGENTS.md record the engineering lesson. Original failures are preserved.

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
