# PuppyPi demo acceptance and evidence

This protocol converts roadmap features into observable application behavior and
research evidence. Record software integration and physical validation separately.

## Acceptance scenarios

| Scenario | Setup and trigger | Required observable result | Failure case to include | Feature IDs |
| --- | --- | --- | --- | --- |
| A Teach and find | Enroll several views, place target plus a look-alike, start search | Correct identity and current station with matching evidence | Target removed; result must not confirm a decoy | F01–F03, F09–F10 |
| B Remember a relocation | Observe at A, move to B, restart the application, request target | History survives; fresh search corrects old location | Occlude A; uncertain observation must not prove absence | F11–F14, F19 |
| C Resolve a request | Two plausible candidates, ambiguous user description | Useful question or new view, followed by resolved/unknown outcome | No answer or contradictory answer; bounded timeout | F16–F19 |
| D Inspect a checklist | Reference layout, one removed item, one misplaced item, supported open container | Separate pass/fail/unknown findings with before/after evidence | Lighting-only change and obstructed view | F20–F25 |
| E Use the body to observe | Partially occluded target and measured feasible poses | Improved useful observation, logged action and measured pose | No feasible improving pose; abstain or request assistance | F26–F27 |
| F Recover and stop | Tag dropout, stale frame, mock/validated communication loss | Defined recovery or stop; operator can cancel | Reconnection must not silently resume stale motion | F04, F06–F07, F28 |
| G Complete and return | Search or inspection finishes away from HOME | Record task result and independently verify return | Return blocked/timeout; preserve task evidence and report return failure | F05, F09 |

Run scenarios in a bounded physical area with measured routes before expanding
navigation. The operator's intervention is part of the recorded result. Do not
discard unsuccessful attempts from the acceptance report.

## Run manifest

New runs belong under ignored `runs/<run-id>/`. Each manifest should include:

```yaml
schema_version: 1
run_id: example-only
feature_ids: [F12, F13]
scenario: B
mode: physical  # synthetic | replay | physics | physical
revision: REQUIRED_COMMIT_SHA
working_tree_dirty: false
dependency_lock_sha256: REQUIRED_HASH
settings_file: settings.json
seed: 42
robot_configuration_file: robot.json
calibration_file: calibration.json
model_manifest_file: models.json
observations_file: observations.jsonl
actions_file: actions.jsonl
result:
  task_outcome: inconclusive  # confirmed | failed | cancelled | inconclusive
  return_home_outcome: not_attempted
  operator_interventions: 0
evidence_directory: evidence
```

This is a proposed manifest format, not an implemented exporter. Fill provenance
from the actual run. Observation records need capture/receive timestamps and
image IDs; action records need requested action, expiry, measured outcome, and
stop reason. Model manifests identify upstream revision, checkpoint hash, and
preprocessing. Do not put credentials in any artifact.

## Feature evidence card

For each demonstration, capture the feature ID, initial conditions, user action,
expected behavior, actual result, run manifest, evidence images/video, and known
limits. Use the same procedure for before/after method comparisons. Keep the
grading-facing explanation grounded in what the operator can actually perform.

## Reporting research results

Separate exact-instance success, correct inspection predicates, successful
navigation, successful return, and human assistance. Specify denominators and
trial counts. Report runtime and network latency on the stated hardware. Include
the conditions under which scores were calibrated and avoid treating correlated
video frames as independent evidence.

Historical output files remain the baseline record. Generate new comparisons
from paired, reproducible runs rather than editing plots or tables by hand.
