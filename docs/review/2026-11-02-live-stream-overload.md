# Critical live-stream scheduling defect and correction

Date: 2026-11-02. Defective base: `74be1ff`. User requested a design correction
and permanent SWE/system-thinking rules. Parent [critical incident](2026-10-31-fatal-critical-lethal-capability-integrity.md)
remains OPEN; this review does not close missing feature/quality obligations.

## Root cause and responsibility

The implementation treated a live perception workload as an ordered replay job:
producer and consumer rates were not matched by a freshness-preserving admission
policy. A two-entry raw queue protected capture from blocking, but a 60-entry
ordered model spool still accumulated obsolete frames. Limiting count did not
bound source age. Increasing hardware speed could hide this mismatch without
repairing the overload policy. The design/implementation responsibility belongs
to the project implementation, not to a paper's accuracy or the user's hardware.

The observed consequence was `TRACKING_CATCHUP_EXCEEDED` and terminated tracking,
not a demonstrated whole-app crash. Camera and other jobs remained available.
The cutoff was failure containment, not a solution to stable live operation.
Original failed [measurements/screenshots](../research/2026-11-02-stream-app/report.md)
are preserved unchanged.

## Authorized correction and engineering rules

The user explicitly approved revising the design after the proposed latest-frame
policy and required system thinking, clean code/architecture and clear patterns.
[ADR/contract revision](../28-live-stream-scheduling.md) precedes this implementation.
[AGENTS.md](../../AGENTS.md) now mandates workload/rate/deadline analysis, explicit
capacity/loss/backpressure at every asynchronous boundary, separation of live and
replay/archive, temporal model contracts, dependency direction, purposeful
patterns and overload/cancellation/restart evidence.

Actual changes: latest-value mailbox; SQLite `FrameInbox` repository; pure
phase-aware scheduling; small state-machine orchestration methods; original
model adapters; schema/profile versioning; generation-safe transactional output;
API/UI scheduling counters. `AssistantError` moves to a framework-independent
module with compatibility re-export. No dependency/framework is added merely to
name a pattern, and GStreamer is not claimed as integrated.

## Verification and limits

[Actual correction report](../research/2026-11-02-tracking-freshness/report.md):
120 s original SAM/Cutie CPU app run, 292 observations, one genuine concurrent
YOLOE/DINOv2/ByteTrack job, peak live pending 1, 172 pending replacements,
no accumulating source age or catch-up failure observed. Stop invalidates late
output. A separate six-second run checks visible UI stop acknowledgement.

This establishes the tested scheduling correction, not unlimited uptime or a
five-FPS/five-minute release. Delivered mask callbacks remain about 2.41 FPS.
A paired upstream sampling replay shows masks differ (six non-seed IoU agreement
0.800–0.992, mean 0.902); background leakage remains. Ground-truth quality,
identity/occlusion recovery and real phone/robot acceptance are unverified.
No paid calls are made, no threshold is widened, no model is replaced and no
failed historical evidence is relabeled as successful.
