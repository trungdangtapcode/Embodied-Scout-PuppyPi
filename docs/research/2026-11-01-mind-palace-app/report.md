# Mind Palace app execution report

Date: 2026-11-01. **Recorded-memory integration executed; broader incident OPEN.**
The user-authorized model profile was `gpt-6-luna`; the selected upstream was the
actual MIT-licensed Mind Palace source at
`b59be261f9508c3a355a8afa0d495eeba0417d68`. No local GPU or physical robot was used.
See the [implementation guide](../../22-mind-palace-app.md),
[manifest and hashes](manifest.json), [fixed tasks](tasks.json),
[paired raw outputs](paired-evaluation.json), [capture outputs](capture-state.json)
and [failure traces](failure-checks.json).

## Executed product path

The actual Preact UI captured six frames from a deterministic pinhole-rendered
camera: three explicit episodes (Early, Middle, Late), two registered viewpoints
(Desk/Front and Shelf/Front). Region names were operator metadata. The six PNGs
were frozen in the same evidence store used by the API and worker. No object
names, expected answers or renderer identities were supplied as model outputs.
Fixture indices in provenance are provenance only, not perception inputs.

A real Huey consumer in a different process claimed each capture job and invoked
the optional model transport. All six descriptions succeeded. Actual source
methods then performed episodic selection, region/view retrieval, image checking,
readiness and answer generation. The worker had the API credential; the app
process explicitly did not. Query results persisted across browser reload and
an app/worker restart. Desktop and 390-pixel phone screenshots were inspected;
there was no horizontal page overflow. Fixed navigation chrome is hidden only
in the cropped panel screenshots to avoid screenshot overlap.

## Paired regression results

These tasks were frozen after development and before this paired run. They are
**post-development synthetic regression**, not a held-out generalization split.
The renderer's labels stayed in evaluation materials. Source-image review checked
the colors/symbols, chronology and cited capture membership; this was an engineering
review, not a blinded annotator study or calibrated accuracy estimate.

Both paths used the same selected/returned model, six raw PNGs and shared model
descriptions. The app could retrieve within a 24-call/8-view budget; the baseline
used one direct reasoning call over all six images. Each call had a 1,024-output-
token cap. Shared capture-description calls are excluded from the table. Tokens
are provider-reported total tokens, not money or unique uncached tokens.

| Task | Product result | Product calls / tokens / wall seconds | Direct-all-images result | Baseline calls / tokens / seconds |
| --- | --- | --- | --- | --- |
| Shelf comparison | Answered Early blue; Middle red + blue; Late blue + green; three valid source citations | 20 / 25,561 / 36.915 | Same supported visual comparison | 1 / 4,054 / 3.806 |
| Desk comparison | Answered Early red; Middle green; Late orange; three valid source citations | 16 / 20,359 / 32.066 | Same supported visual comparison | 1 / 4,028 / 3.093 |
| Purple-cup witness | `inconclusive`; no admitted positive witness; no between-capture absence claim | 20 / 18,443 / 37.502 | `answerable=no`, no citations | 1 / 3,796 / 6.258 |

**No superiority claim is supported.** Direct-all-images was faster and consumed
fewer reported tokens on this tiny input. The purpose of this run is to establish
real app/source/model execution and conservative evidence behavior. Larger memory,
paired budgets and a held-out real-room dataset are needed to evaluate retrieval
benefit. Production never invokes this baseline when Mind Palace fails.

The primary replay plus occlusion check and baseline produced **71 completed,
recorded model calls / 85,274 reported tokens**, all returned as `gpt-6-luna`.
The cancelled in-flight request has unknown usage and is excluded; an already
sent request may still be billed. Development calls below are separate and excluded.

## Failure and independence checks

| Case | Actual observation | Evidence |
| --- | --- | --- |
| No source checkout | Separate worker exits 1, `UPSTREAM_UNAVAILABLE`; zero model calls | [Startup records](startup-failures.json) |
| No API key | Separate worker exits 1, `MODEL_KEY_REQUIRED`; zero model calls | [Startup records](startup-failures.json) |
| Cancel active job | Observed `running` with a model stage started; cancelled; five seconds later still `cancelled`, no result | [Failure traces](failure-checks.json) |
| Covered camera frame | New fourth episode, actual model description says uniform gray/no objects; question ends `inconclusive`, inspected gray image retained | [Failure traces](failure-checks.json), [covered input](inputs/scene-6.png) |
| Missing snapshot image | Temporarily hide one source PNG before submitting a new question; job fails `MEMORY_IMAGE_MISSING`, no model step; source restored in `finally` | [Failure traces](failure-checks.json) |
| Stop during inference | Runner stop call completes in 0.0043 seconds while model task was running; no physical actuation | [Failure traces](failure-checks.json) |
| UI control during inference | Synthetic UI arm/hold/release followed by stop: HTTP 200 in 13.932 ms, disarmed, one inference job pending | [Independent control record](stop-during-inference.json) |
| Persistence / duplicate / late completion | Offline regression tests cover reopen, mode isolation, frozen snapshots/profiles, idempotent retry, interrupted-job reconciliation, and cancellation preventing description/result insertion | `tests/test_memory_workflow.py` |
| Malformed output / wrong model | Exact detection/readiness enums, empty selection and unknown citations rejected before upstream conversion; wrong model and incomplete output fail | `tests/test_memory_workflow.py` |

The gray-image description returned visibility `clear` despite containing no
scene information. That label is a model hypothesis, not evaluated visibility
calibration. No target witness was admitted and no hidden object state was inferred.
Worker restart reconciliation is covered offline; a hard process crash during a
billable provider call was not deliberately induced or claimed exactly-once.

## Retained development evidence

An [initial multi-episode run](development-inconclusive.json) inspected all six
captures but returned `inconclusive`: local checks tried to answer the global
question. It was retained, then the adapter clarified local visual-target checking
versus later global readiness. No response was replaced with a positive fixture.
A [subsequent development run](development-multi-episode.json) executed 22 model
calls and answered the full three-episode/two-region comparison with six validated
citations. These development traces are distinct from the final paired regression.

## Verification and outstanding gates

`make check`, `make test` (82 passed), `make app-build`, `make app-test` (6 Chromium
tests) and `make build` passed. One pre-existing Starlette/httpx deprecation warning
remains. Default tests do not call a model, download weights, use GPU/ROS or actuate
hardware. The opt-in acceptance runner exited successfully and stopped its own
worker/app; a separate persisted-answer screenshot check also stopped its children.

Original benchmark reproduction is still blocked by the previously observed
Google Drive scene-data quota. Real-room quality, automatic localization/region
formation, exact-instance tracking, active acquisition, autonomous navigation,
learned locomotion and physical safety/performance validation are not delivered
by this slice. No learned predictive world model is claimed. The wider critical
incident and user-assigned 0/10 delivery rating remain unchanged.

After model acceptance, the code was formatted and unused imports removed. A
subsequent offline regression fixed capture-description lookup beyond the
25-row snapshot window: the worker now fetches the job's exact capture ID, and
the overview shows recent captures first. That boundary was tested with 26
viewpoints. The model prompts/retrieval method were unchanged; paid model
acceptance was not repeated solely for this storage-read correction. The manifest
distinguishes execution-time source hashes from final source hashes.
