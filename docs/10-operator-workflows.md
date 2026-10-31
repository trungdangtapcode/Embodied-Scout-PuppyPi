# Persistent object memory and inspection workflows

These local Python/CLI workflows are implemented. They need neither a robot nor
a model download. Inspection currently evaluates **recorded assertions**; it does
not infer absence from an image or execute a patrol. The operator supplies the
assertion, capture time, quality, and visibility. Automated verifier integration
and physical validation remain separate milestones.

## Run the complete synthetic example

```bash
make setup
make demo-assistant
```

Open the printed `report.html` path. Each invocation creates a new directory under
ignored `runs/assistant-demo/`, enrolls four rendered objects, records observations,
closes and reopens SQLite, and exports a report with **one pass, two failures, and
one unknown**. The failures represent a misplaced object and an annotated missing
object; the unknown represents an obscured view. A location history demonstrates
an old sighting at A followed by a new sighting at B.

The run includes `manifest.json`, `location-history.json`, a persistent database,
and a portable report folder. The manifest records the Git revision/dirty state,
lock hash, seed, settings, encoder signature, object IDs, and results. Assertions
are scripted on rendered crops. This checks application plumbing and evidence
rules; it is not an object-recognition accuracy experiment or a robot demo.

## Enroll and manage objects

Use the isolated interpreter from the repository root:

```bash
export TEACH_FIND_DATA_DIR=data/assistant
.venv-dev/bin/python -m teach_and_find objects teach --name "Tool pouch" \
  --images data/front.png data/side.png --angles 0 60
.venv-dev/bin/python -m teach_and_find objects list
```

Inputs are tightly cropped BGR-readable object images. Copy the returned `id`
into a shell variable, replacing the example value below:

```bash
OBJECT_ID='replace-with-returned-object-id'
.venv-dev/bin/python -m teach_and_find objects rename "$OBJECT_ID" "Blue tool pouch"
.venv-dev/bin/python -m teach_and_find objects teach --object-id "$OBJECT_ID" \
  --name "Blue tool pouch" --images data/front.png data/side.png --angles 0 60
.venv-dev/bin/python -m teach_and_find objects match data/candidate.png
```

Renaming and replacing reference views preserve identity and observation history.
Active names are unique after whitespace normalization and case folding. Matching
returns ranked `candidate_only` results; a score never becomes an observation or
an automatic confirmation. The inherited `calibrated_score` field is heuristic.

Archive an object to remove it from the active library while retaining evidence:

```bash
.venv-dev/bin/python -m teach_and_find objects archive "$OBJECT_ID"
.venv-dev/bin/python -m teach_and_find objects list --archived
```

Do this after the inspection example if using the same object. Archive is a soft
removal, not an erase operation. There is no restore or permanent-delete command
in this release. Existing checklist entries for an archived object yield unknown.

## Record and inspect observations

Use the actual image capture timestamp, including its timezone. The historical
timestamp below is an example; do not substitute upload time for capture time.

```bash
.venv-dev/bin/python -m teach_and_find observe --object-id "$OBJECT_ID" \
  --station Station_A --assertion present --image data/front.png \
  --captured-at 2026-10-31T09:00:00+09:00 --mode replay
.venv-dev/bin/python -m teach_and_find history "$OBJECT_ID"
.venv-dev/bin/python -m teach_and_find last-seen "$OBJECT_ID" --mode replay
```

Each observation stores a UUID, capture and recording timestamps, station, raw
assertion, image hash, source, quality, visibility, and evidence mode. History is
ordered by capture time. `last-seen` is a historical positive sighting, **not a
claim about the current location**; the latest observation is returned separately.

Available assertions are `present`, `absent`, and `unknown`. An obscured image
must be annotated unknown or assigned appropriately low visibility. Quality and
visibility gates are uncalibrated heuristic inputs, not computed probabilities.
The defaults are quality >= 0.60 and visibility >= 0.80. CLI observations always
identify their source as `operator`. `--mode` is explicit provenance supplied by
the caller: synthetic, prerecorded replay, or physical capture. It does not
authenticate evidence or mark the feature hardware verified.

## Create a checklist and export evidence

```bash
.venv-dev/bin/python -m teach_and_find checklists create --name "Desk inspection" \
  --item "$OBJECT_ID@Station_A"
CHECKLIST_ID='replace-with-returned-checklist-id'
.venv-dev/bin/python -m teach_and_find inspect "$CHECKLIST_ID" \
  --mode replay --as-of 2026-10-31T09:02:00+09:00 --max-age 300
REPORT_ID='replace-with-returned-report-id'
.venv-dev/bin/python -m teach_and_find export "$REPORT_ID" --output runs/desk-report
```

Repeat `--item` for additional objects. Checklists snapshot the object name and
enrollment image. `inspect` assesses matching-mode observations in the capture
window; it does not collect new evidence. Omit `--as-of` to assess the current
window. A historical cutoff filters capture times in the database available now;
it does not reconstruct what the system knew at that past processing time.

Rules use the latest assertion per station and the newest reliable positive
sighting. A later sighting supersedes an older location. Clearing that later
location cannot resurrect the old one. Conflicting simultaneous assertions or
locations yield unknown, and a newer unclear expected-station view blocks an
older misplacement conclusion. A sufficiently visible recorded absence at the
expected station yields missing when no surviving newer location establishes
misplacement. These are deterministic evidence rules, not a learned world model.

Export creates HTML, JSON, and relative PNG evidence paths in a new directory.
The report preserves its finding/name/evidence snapshot after library changes.
The export fails on missing/corrupt evidence or an existing destination. Copy the
whole report folder to retain the images. It contains the selected source images;
the CLI does not publish or upload it.

## Persistence and integration contract

SQLite `user_version` migrations create object/observation tables (v1), then
checklists/report snapshots (v2), then observation provenance JSON (v3). Legacy
records retain empty metadata rather than invented camera details. A newer
unknown schema is rejected. Images are
lossless PNGs addressed by SHA-256; reads and exports validate integrity. SQLite
changes are transactional. An interrupted/failed write may leave an unreferenced
image file; automatic garbage collection is not implemented.

Embeddings include the model/preprocessing signature and dimensionality. Matching
and restoring the existing `ObjectMemoryBank` reject incompatible active records.
The default spatial signature includes its preprocessing version and crop size.
Torch enrollment requires `TEACH_FIND_ENCODER_REVISION` in addition to existing
backend/repository/model settings. The caller must pin and verify that revision;
the string alone does not verify a downloaded checkpoint. Automatic re-embedding
or cross-model conversion is not implemented.

`ObjectLibrary.memory_bank(mode=...)` adapts persisted objects and same-mode
positive station counts to the existing planner/verifier interface. It is a
reusable boundary; the legacy mission FSM has not yet been wired to write these
observations. Model loading occurs when the CLI builds its library, so keep the
default spatial backend for offline workflows.

## Software acceptance evidence

| Feature | Entry point | Evidence and failure coverage |
| --- | --- | --- |
| F01, F10 | `objects teach/list/rename/archive` | [Library tests](../tests/test_library.py): restart, stable IDs, replacement, duplicate-name rollback, model mismatch |
| F11, F14 | `history`, `last-seen` | Capture ordering, historical-versus-current distinction, mode isolation |
| F13 | `observe` plus inspection gates | [Inspection tests](../tests/test_inspection.py): obscured views retain unknown; raw assertion preserved |
| F20 | `checklists create/list` | Durable rules and enrollment references; archived identities handled |
| F21, F23 | `inspect` | Recorded presence/absence/misplacement rules; stale and conflicting facts, cleared locations |
| F25 | `export` | Immutable snapshots, escaped HTML, portable images, missing-image/overwrite errors |
| Operator integration | `python -m teach_and_find` | [CLI test](../tests/test_cli.py): independent processes through enrollment, history, checklist, export, archive |

F13/F21/F23 remain prototypes: assigning assertions and visibility is manual in
the supported CLI. No claim of autonomous visual inspection follows from these
tests. No feature in this slice is hardware verified.
