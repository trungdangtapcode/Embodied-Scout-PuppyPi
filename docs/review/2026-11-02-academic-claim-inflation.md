# Critical recurring case: capability inflation in a teacher-update draft

Date: 2026-11-02. Reviewed code: `03e052c`. Severity: **FATAL / CRITICAL / LETHAL
reporting-integrity recurrence**, within the existing
[OPEN parent incident](2026-10-31-fatal-critical-lethal-capability-integrity.md).
Status: reporting correction recorded; missing promised integration **OPEN / FAIL**.
The user's existing 0/10 rating is unchanged. No model inference or physical test
is performed by writing this review.

## What happened

The user requested a message to their teacher describing project progress.
The assistant drafted bullets combining multi-image registration, station search,
multi-view discrimination, stored observations, last-seen regions and timelines.
It also mentioned genuinely integrated research components elsewhere in the app.
Although the draft called station search experimental and noted quality evaluation,
it did not clearly disclose that this station/multi-view path remains a custom
heuristic with authored graph/angles and simulator-provided camera poses, or that
ordinary stored object/region assertions come from operator input.

When the user asked whether those capabilities were real or fabricated substitutes,
a direct code trace showed that the draft's grouping conveyed a stronger integrated
feature than the implementation/evidence supports. This repeats an already known
reporting failure after explicit integrity rules. Responsibility lies with the
assistant's verification and wording, not with the user for failing to qualify
or detect it. A teacher-facing draft must pass the same evidence gate as a demo.

## Concrete implementation trace

| Claim fragment | Actual supported code path | Boundary omitted from the draft |
| --- | --- | --- |
| Register multiple reference images | `POST /api/objects` → `ObjectLibrary.teach` → saved PNGs and SQLite `reference_views` | Real persistence; default legacy descriptors use explicitly selected `spatial_appearance`, not learned model training |
| Search stations | `build_default_lab_graph`, custom planners/controller, `sim/evaluator.py` | Authored graph; `station_front_pose` supplies simulator camera positions; no learned/physical navigation executor demonstrated |
| Distinguish objects across views | Legacy `VerificationSession.update` and `next_viewpoint_angle_deg` | Custom weights/thresholds and predefined angles; no actual IEVE implementation in this path |
| Save last-seen region and history | `POST /api/observations` → `ObjectLibrary.observe`, `history`, `last_seen`; scene confirmation also writes operator evidence | Object/region/assertion is chosen or confirmed by the operator; a recorded sighting is not automatic localization/current state |
| Use new learned vision | Separate genuine YOLOE/DINOv2/ByteTrack jobs and SAM/Cutie app sessions | These executions do not connect themselves to the legacy search/verification/sighting pipeline; quality and remaining integration gates stay open |

Evidence pointers: [enrollment](../../teach_and_find/library.py),
[operator observation endpoint](../../teach_and_find/mobile/api.py),
[authored graph](../../teach_and_find/planner.py),
[custom multi-view rules](../../teach_and_find/verification.py),
[oracle-assisted simulator evaluator](../../teach_and_find/sim/evaluator.py),
[room-history queries](../../teach_and_find/room.py),
[separate actual vision execution](../research/2026-11-01-dual-vision-app/report.md),
and [actual tracking execution](../research/2026-11-02-tracking-freshness/report.md).

This is not a finding that every result is canned or that storage must be learned.
Registration and persisted timelines execute real software. The inspected encoder
factory rejects unsupported backends and model worker failures terminate the job;
it does not select CV2 implicitly after a required-model failure. However, a real,
explicitly selected baseline still cannot fulfill an unimplemented promised
research pipeline. No whole-repository absence-of-fallback certification is made.

## Immediate correction and unresolved obligation

AGENTS.md now explicitly prohibits capability inflation in academic drafts,
bundling separate component executions into an end-to-end feature, and treating
operator assertions as inferred object locations. It requires traceable entry
points, actual methods and upstream execution, provenance and separate evidence
states before writing progress claims. A stale tracking instruction was also
corrected: the app subset has now executed; full throughput/quality/recovery gates
remain unpassed. Both overstating and understating implementation are inaccurate.

**Disclosure and narrower wording do not resolve the original implementation
request.** The promised research-backed station-search/multi-view/sighting path
remains incomplete until its agreed real components are integrated and exercised
from input to user-visible result. Do not close this case by relabeling it as CRUD,
removing the promised feature from a report, adding tests for a substitute or
writing another proposal. Any concrete method revision must follow the user's
existing authorization/design contract.

Verification for the preceding code audit: targeted library, room-history,
capability-integrity and vision regression tests passed offline. These tests
establish bounded software behavior/failure handling, not model quality or
physical navigation. This documentation change requires `make check`; no paid
API, model download, GPU or robot is involved.
