# Room memory: executed upstream validation

Date: 2026-10-31. This is execution evidence, not an app-completion claim.
The [critical incident](review/2026-10-31-fatal-critical-lethal-capability-integrity.md)
remains **OPEN / FAIL** for the missing application integration.

## Recommendation and supported scope

Use **Enter the Mind Palace: Reasoning and Planning for Long-term Active Embodied
Question Answering** as the upstream candidate for the memory/reasoning layer:
[paper](https://arxiv.org/abs/2507.12846),
[official repository](https://github.com/mind-palace-laeqa/benchmark),
tested revision `b59be261f9508c3a355a8afa0d495eeba0417d68`, MIT code license.

This recommendation has a narrow executable basis: actual upstream components
completed a public-image memory/reasoning replay using **GPT-4o through OpenAI**,
then the user-selected **`gpt-6-luna`** with an explicit transport adapter.
It is not a claim that the complete LA-EQA benchmark, automatic scene construction,
long-term memory quality or the PuppyPi app integration works. The app still uses
its original heuristic/annotation-backed flow. No feature status is promoted.

Mind Palace is a structured episodic memory and reasoning/planning method. Its
class named `WorldModel` retrieves recorded images and simulates motion between
known nodes; this does not establish a learned predictive world model or a live
PuppyPi navigation executor. Paper-repository reuse does not remove those boundaries.

## What actually ran

| Experiment | Observed result | What it establishes |
| --- | --- | --- |
| Install Mind Palace from its `pyproject.toml` in an isolated Python 3.12 CPU environment | Installed and imported; CPU Torch used | The tested package/dependency profile can load; this differs from the author's pinned Python 3.9 Conda environment |
| Execute the original example notebook with `nbclient` | **FAIL**: missing `place_nodes_092-hm3d-eF36g7L6Z9M_0.pkl` | Reference benchmark was not reproduced |
| Retrieve the linked benchmark scene archive | **FAIL**: Google Drive reports `Quota exceeded` | The required scene files were not obtained; no substitute is counted as a benchmark pass |
| First API diagnostic through the original interface | API returned a response, but **FAIL** at strict JSON parsing because it contained Markdown fences | Connection and API access work; parser robustness is not established |
| Explicit one-image component replay, first run | **PASS_COMPONENT_REPLAY**, answer `Two cats`, 47.560 s | Real visual inference and upstream memory/reasoning calls completed on one case |
| Repeat using the committed reproducer | **PASS_COMPONENT_REPLAY**, answer `Two cats`, 50.727 s | The standalone reproducer exercised the same declared component path |
| User-selected `gpt-6-luna`, with the declared Chat Completions adapter | **PASS_COMPONENT_REPLAY**, answer `Two cats were visible on the sofa.`, 33.069 s | Eight actual API calls returned `gpt-6-luna`; four included image input; same one-case limitations apply |
| Run reproducer without a key | **Expected FAIL**, exit code 2, `OPENAI_API_KEY is required; no fallback` | Missing credentials do not select mock output or a heuristic backend |
| Install ReMEmbR, revision `964faab296fe70f8a8dbb9135adf20fecb758525`, then initialize `ReMEmbRAgent(llm_type='gpt-4o')` | Dependencies installed; **FAIL** at initialization: `No correct LLM provided` | This checkout's OpenAI branch contains a TODO and does not support that requested profile as shipped |
| Import ReMEmbR's VILA captioner | **FAIL**: `No module named 'llava'` | Its separately installed VILA stack is still missing; no full ReMEmbR run is claimed |

The ReMEmbR results refer to that checkout and profile, not a universal claim that
ReMEmbR cannot run. Its repository supports other providers, but no backend was
substituted to turn the OpenAI-profile failure into a success.

## Input, actual method and limitations

The input is a public 640 × 480 image from the
[Hugging Face documentation-images dataset](https://huggingface.co/datasets/huggingface/documentation-images/blob/main/coco_sample.png).
SHA-256: `cf6f3c4befa148732c7453e0de5afab00f682427435fead2d88b07a9615cdac2`.
The photo visibly contains two cats on a pink sofa. It was downloaded only into
ignored `runs/`; it is not redistributed in this evidence bundle. It is a test
photo, not a PuppyPi camera capture. Its capture time is unknown.

The question was: **Which animals were visible on the sofa in the recorded image?**
The answer was not entered into the harness or an observation database. The tested
path, using unmodified tracked upstream source, was:

1. `OpenAIInterface` sends the image to GPT-4o and parses visible-object descriptions.
2. A small declared input adapter places those model-generated descriptions into
   upstream `PlaceNode`, `RoomNode` and `SceneGraph` records.
3. `EQAReasoning.object_identification` determines the visual target.
4. `EpisodicExploration.episodic_reasoning_v2` selects the recorded episode.
5. `RoomExploration.plan` selects the room; upstream direct place retrieval selects
   the stored viewpoint. The wrapper deliberately does not call the place planner's
   unvisited-node fallback and fails on invalid or empty selections.
6. `WorldModel.explore` retrieves the stored image, with no motion call.
7. `MindPalaceExploration.vlm_image_analysis` makes a real VLM call to verify the
   requested content. `BeliefManager.update_history` records the returned insight.
8. `EQAReasoning` checks readiness and answers from the retrieved observation.

The one room and one viewpoint have nominal coordinates supplied by the harness.
They are not measured geometry or inferred room topology. `replay_step_0` names
replay order, not an actual capture timestamp. The initial captioning adapter is
project-owned orchestration through the upstream API interface; it is not the
original dataset loader or an implementation of automatic multi-room reconstruction.

There is only one candidate episode, room and viewpoint. This case cannot show
retrieval discrimination, long-horizon reasoning, active acquisition efficiency,
tracking, exact-instance recognition, negative detection, temporal coverage or
calibrated confidence. The upstream room scores remain uncalibrated model outputs.
The unchanged reference notebook still fails. These are separate experiment results,
not a fallback claim that a custom replay reproduces the full benchmark.

## GPU and deployment

No local GPU inference was used. `CUDA_VISIBLE_DEVICES=-1` was set and Torch in
the isolated environment is a CPU build. GPT-4o inference runs through the OpenAI
API; the local host handles graphs, control flow and image preparation. The user
explicitly authorized using the API and identified the key in `bashrc`. The
reproducer optionally loads that configuration without printing or saving it.

This profile needs API access and incurs API usage. It does not host a local LLM
or VLM, and no key or credentials are committed. Optional RAM-based perception,
local pretrained backbones or a later mapping stack would have their own resource
requirements; they were not executed in this experiment. The Pi runs no new service.

## Reproduce the observed component experiment

This section retains the original GPT-4o experiment at source commit `0c8c749`.
Its original artifact manifest hashes that historical script. The current
reproducer requires explicit `--model` and `--api-mode`; to use its historical
transport, append `--model gpt-4o --api-mode upstream` to the original command
below. Do not compare the historical script hash with a later modified script.
The current user-selected Luna command and its separate manifest follow below.

The reproducible entry point is
[research_mind_palace_replay.py](../scripts/research_mind_palace_replay.py).
It is an explicitly invoked research experiment; default tests do not call it
or paid APIs. Keep all checkouts, downloaded inputs and environments in ignored
`runs/room-upstream-audit/`. Preserve `.venv/` and `.venv-dev/`.

For a fresh checkout of the experiment dependencies:

```bash
mkdir -p runs/room-upstream-audit
git clone https://github.com/mind-palace-laeqa/benchmark.git runs/room-upstream-audit/mind-palace
git -C runs/room-upstream-audit/mind-palace checkout b59be261f9508c3a355a8afa0d495eeba0417d68
UV_PROJECT_ENVIRONMENT=.venv-dev uv venv --python 3.12 runs/room-upstream-audit/.venv-mind-palace
UV_PROJECT_ENVIRONMENT=.venv-dev uv pip install --python runs/room-upstream-audit/.venv-mind-palace/bin/python --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match -r docs/research/2026-10-31-room-memory-execution/requirements-py312-cpu.txt
UV_PROJECT_ENVIRONMENT=.venv-dev uv pip install --python runs/room-upstream-audit/.venv-mind-palace/bin/python --no-deps -e runs/room-upstream-audit/mind-palace
curl --fail --location --connect-timeout 10 --max-time 120 https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/coco_sample.png --output runs/room-upstream-audit/coco_sample.png
```

The environments/checkouts already exist on the tested host; do not recreate them
just to run the following command. Verify the input hash above before comparing
with the saved evidence. This command was executed successfully:

```bash
CUDA_VISIBLE_DEVICES=-1 MPLBACKEND=Agg timeout 300 \
  runs/room-upstream-audit/.venv-mind-palace/bin/python \
  scripts/research_mind_palace_replay.py \
  --upstream runs/room-upstream-audit/mind-palace \
  --revision b59be261f9508c3a355a8afa0d495eeba0417d68 \
  --image runs/room-upstream-audit/coco_sample.png \
  --source-url https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/coco_sample.png \
  --question 'Which animals were visible on the sofa in the recorded image?' \
  --output runs/room-upstream-audit/reproducible-replay \
  --from-bashrc
```

If credentials are already exported, omit `--from-bashrc`. The script checks the
upstream revision, tracked-source cleanliness and imported module location. It
returns a nonzero exit on a failed component run and writes `result.json` and
`replay.log` into the chosen output directory. Model responses remain
nondeterministic; do not treat the two observed answers as a guarantee.

## Current user-selected model: GPT-6 Luna

The user confirmed the exact model ID `gpt-6-luna` after the initial misspelled
`gpt-6-6luna` returned `404 model_not_found`. The API model catalog listed the
correct ID. All eight calls in the successful Luna replay returned `gpt-6-luna`,
including four requests with image input. Observed elapsed time was 33.069 s;
reported aggregate usage was 4,331 tokens. These observations are not latency or
quality benchmarks, and no local GPU was used.

The repository's graph, retrieval and reasoning code is still imported directly
from the pinned upstream checkout. A project-owned transport override applies the
selected model to every upstream interface, uses `max_completion_tokens` instead
of the legacy limit, omits the legacy seed, and requests a JSON object. Reasoning
effort `none` preserves the original non-reasoning workload role; the upstream
temperature of 0.2 and output limit of 512 are retained for this profile. Request
timeout is explicitly 60 seconds, with SDK retries disabled. See the official
[Luna model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna),
[migration parameters](https://developers.openai.com/api/docs/guides/latest-model)
and [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

This is a declared model/transport adaptation of upstream components, not an
unchanged reproduction of the paper's GPT-4o setup. Source files in the upstream
checkout are unchanged. The wrapper fails on a wrong returned model, incomplete
or refused output, empty output, invalid selection, API error or missing key.
It never retries with GPT-4o or a mock. Model selection is explicit; the script
has no implicit model default. The prior GPT-4o evidence remains historical.

This command was executed successfully:

```bash
CUDA_VISIBLE_DEVICES=-1 MPLBACKEND=Agg timeout 300 \
  runs/room-upstream-audit/.venv-mind-palace/bin/python \
  scripts/research_mind_palace_replay.py \
  --upstream runs/room-upstream-audit/mind-palace \
  --revision b59be261f9508c3a355a8afa0d495eeba0417d68 \
  --image runs/room-upstream-audit/coco_sample.png \
  --source-url https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/coco_sample.png \
  --question 'Which animals were visible on the sofa in the recorded image?' \
  --output runs/room-upstream-audit/luna-replay \
  --model gpt-6-luna --api-mode chat-completions \
  --reasoning-effort none --request-timeout-s 60 --from-bashrc
```

Inspect [the actual Luna output](research/2026-10-31-room-memory-luna/component-replay.json)
and [its separate manifest](research/2026-10-31-room-memory-luna/manifest.json).
Seven new offline regression cases cover model routing, sampling compatibility,
terminal request failure and rejecting wrong-model/truncated/refused/empty output.
The updated missing-key command was also executed and exited 2 without API use.
App integration and the original benchmark remain unverified/failed as recorded above.

## Persisted evidence and next acceptance gate

- [Observed component output](research/2026-10-31-room-memory-execution/component-replay.json)
- [Execution and failure summary](research/2026-10-31-room-memory-execution/execution-summary.json)
- [Artifact/source manifest](research/2026-10-31-room-memory-execution/manifest.json)
- [Observed Python 3.12 CPU environment](research/2026-10-31-room-memory-execution/requirements-py312-cpu.txt)

Raw traces and the failed executed notebook remain under ignored
`runs/room-upstream-audit/`; summary artifacts above are the portable record.
No weights, private camera recordings or complete upstream source trees are committed.

Next application gate: implement a versioned adapter from actual PuppyPi evidence
to upstream episodic records, invoke these actual components from the app,
retain source-image and model provenance, and report missing/invalid inputs or
API/parser failures without fallback. Then evaluate multiple episodes and
confusing/missing objects. Automatic geometry and physical acquisition remain
separate requirements. The existing heuristic app is not silently replaced or
reclassified by this experiment, and the critical review is not closed.
