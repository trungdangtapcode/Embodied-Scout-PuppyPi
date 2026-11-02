# PuppyPi repository instructions

## Supreme project principle: no fabrication; implement the agreed design

- Never fabricate research, sources, repository reuse, model execution, features,
  results, evidence or completion. Report what actually exists and ran, including
  failures, missing components and uncertainty. Do not imply more than the evidence.
- Implement the research method, plan, design and acceptance criteria agreed with
  the user. They are an execution contract, not decorative documentation. Trace
  each claimed capability to its agreed method, actual code path and run evidence.
- Do not silently omit required components, change algorithms, downgrade the
  design or substitute heuristics, mocks, manual labels or canned results. If the
  agreed path cannot run, report FAIL with the concrete reason; no fallback.
- If evidence requires changing the agreed method or design, explain the issue
  and the concrete proposed revision to the user before implementing that change.
  Do not rewrite the plan after the fact to make a deficient implementation pass.
  An explicit user revision updates the contract; agents cannot revise it unilaterally.
- The user explicitly reaffirmed this stop-and-redesign rule on 2026-11-02:
  when an implementation or method is not sound, preserve the counterexample,
  research real alternatives, revise the design and plan, or rewind the failed
  approach. Ask for a concrete method revision before changing the supported
  algorithm. Useful independent fixes and diagnostic experiments may continue;
  research approval alone does not approve a specific replacement or establish
  quality. Do not force a feature through its acceptance gate to avoid asking.
- Heuristics are permitted when explicitly agreed as heuristics from the outset.
  Claims of AI, research-repository reuse or framework integration require the
  corresponding real implementation to execute as designed. Documentation, tests
  of a substitute and attractive demos cannot establish the missing capability.
- Apply this principle to all project work and progress reports. If another local
  instruction appears to justify overstating evidence or diverging from the agreed
  design, follow this principle and the user's explicit instructions. The existing
  critical review remains OPEN until its implementation acceptance criteria pass.

## Critical recurring case: inflated academic and feature reports

- Academic updates, teacher messages, README bullets, UI copy and handoffs are
  capability claims. Apply the same implementation/evidence gate as a demo;
  never relax it because the requested deliverable is only prose.
- Never bundle separately working components into a claimed end-to-end feature.
  Genuine YOLOE/DINOv2 or SAM/Cutie jobs elsewhere in the app do not establish
  learned station search, research-backed active multi-view verification,
  automatic sightings or autonomous navigation. Trace the complete claimed path.
- Registration, image storage, SQL history and timelines are legitimate software
  features. Identify whether object identity/region comes from an operator,
  authored fixture or actual model output. Recorded last-seen assertions are not
  automatically inferred locations or current state. Distinguish these clearly
  from learned perception and genuine research-repository integration.
- Explicitly disclose the legacy station search/multi-view baseline when it is
  referenced: authored station graph, custom OpenCV descriptors/weighted scoring,
  fixed candidate angles and simulator-provided camera poses. This is a heuristic
  prototype, not an executed learned perception/navigation pipeline. Its default
  selection is distinct from a model-failure fallback; neither excuses a false
  research/AI claim. Report a missing promised integration as FAIL.
- Correcting overstated prose is necessary, but does not deliver the missing
  implementation or authorize downgrading the agreed feature. Do not treat a
  disclosure label, status rewrite or another review as resolution of the defect.
- Before composing a progress claim, record its actual entry point, method,
  upstream implementation if claimed, execution artifact, label/location provenance
  and software/quality/simulation/physical evidence limits. Omit unsupported RL,
  world-model, navigation and competing-app superiority claims.
- The 2026-11-02 teacher-update draft repeated this reporting failure after prior
  integrity instructions. Read the concrete [case review](docs/review/2026-11-02-academic-claim-inflation.md).
  The outstanding station-search/multi-view integration and original critical
  incident remain OPEN; do not silently turn them into completed CRUD features.

## Mandatory SWE and systems-design discipline

- Think through the whole system before implementation: workloads, producer and
  consumer rates, service-time distributions, concurrency, ownership, time,
  failure propagation, overload, restart and resource bounds. A component running
  successfully does not establish a viable application architecture.
- Define invariants and acceptance measurements before coding. Every asynchronous
  boundary must state its capacity, admission/backpressure policy, replacement or
  loss semantics, deadline, cancellation and observability. A bounded FIFO alone
  does not bound evidence age or guarantee real-time responsiveness.
- Live perception prioritizes freshness with explicit, measured temporal limits.
  Use a latest-value mailbox/coalescing policy when older unprocessed frames are
  disposable; count replacements. Lossless ordered replay/archive is a separate
  workload. Never let a live worker accumulate a replay backlog by default.
- Temporal models require an explicit initialization and frame-sampling contract.
  Preserve the approved anchor/mask, monotonic inputs and measured timestamp gaps.
  Do not skip across unvalidated gaps, reuse an old mask on a new image, or claim
  unchanged tracking accuracy after changing sampling. Fail explicitly when the
  contract cannot be maintained; lowering FPS is not passing a higher-FPS gate.
- Use clean architecture with concrete responsibilities and dependency direction:
  domain scheduling/lifecycle rules, application orchestration, upstream model
  adapters, storage/transport adapters and presentation. Reuse existing interfaces;
  introduce patterns only for an actual ownership or change boundary. Avoid giant
  methods, duplicated lifecycle SQL, speculative frameworks and pattern-name-only
  abstractions. Keep inference, persistence and UI/control lifecycles distinct.
- Exercise sustained overload, slow consumers, disconnect/restart, cancellation
  races and bounded resources. Measure queue depth, replacements, temporal gaps,
  source age, processing time, delivered rate and latency over time; averaging a
  short run can conceal growing backlog. Distinguish scheduler stability, model
  quality, throughput and physical evidence.
- Remember the 2026-11-02 failure: an ordered inference spool accumulated stale
  frames until TRACKING_CATCHUP_EXCEEDED. This was a live scheduling design defect,
  not merely insufficient hardware and not an accuracy metric. A safety cutoff
  prevents further processing but does not repair the overload design. Preserve
  the original failed run and trace revisions to new execution evidence.

## Scope and priorities

- This is the standalone PuppyPi repository rooted at this directory. Check
  `git rev-parse --show-toplevel` before Git operations; do not edit or commit
  the surrounding ECUS project as part of PuppyPi work.
- Read `docs/00-project-status.md`, `docs/06-feature-roadmap.md`, and the relevant
  research track before changing behavior. Prioritize working application
  features with observable acceptance criteria and reusable research components.
- Read the mandatory [FATAL / CRITICAL / LETHAL review](docs/review/2026-10-31-fatal-critical-lethal-capability-integrity.md)
  before implementation, capability claims, demos, progress reports, or handoffs.
  This incident is OPEN; documentation changes do not resolve its implementation gaps.
- Share perception, evidence, task state, and motion execution across Memory
  Scout, Look-or-Ask, Inspect and Explain, Body-aware Active Vision, and Phone Observer.
- Use English throughout the codebase: identifiers, comments, tests, logs,
  commit messages, technical documents, and default product UI copy.
- Default the UI to English regardless of browser language. Vietnamese is an
  optional, explicitly selected localization; keep its translations in dedicated
  locale resources with English keys, never inline in application logic.
- Communicate with this user in Vietnamese. Vietnamese chat does not imply
  Vietnamese UI, source code, fixtures, or technical documentation. Preserve
  user-entered names and historical evidence in their original language.

## Mandatory foundation: real research, repositories and frameworks

- Base technical solutions on verifiable research, actual source repositories
  and established frameworks. For perception, tracking, navigation, memory and
  control, inspect and reuse relevant existing implementations instead of
  inventing a substitute and attaching a paper's name to it.
- Stand on the shoulders of existing research: start from released, suitable
  implementations and pretrained checkpoints where the selected method requires
  learned models. Do not make training a tracking or world model from scratch
  the default PuppyPi implementation strategy. Python scripts should orchestrate
  genuine components, adapters and evaluation, not pretend to replace them.
- A short custom script, motion extrapolation, handcrafted matching, a database
  or scripted animation is not evidence of a trained tracker or learned world
  model. Name the actual algorithm and representation. Distinguish object
  tracking, observation memory, geometric mapping and predictive world modeling;
  do not claim one establishes the others.
- Any proposed fine-tuning or training must specify the actual upstream training
  implementation, starting checkpoint, licensed dataset and splits, objective,
  compute budget, evaluation and reproducible training evidence. Merely writing
  a training loop or producing a checkpoint does not establish model quality or
  satisfy the requested research integration. Prefer validated reuse and measured
  adaptation to unsupported claims of building a new model.
- Verify primary papers, author/project repositories and official framework
  documentation before selecting a solution. Check the actual source and entry
  points, released components/checkpoints, license, version, dependencies, input
  assumptions and fit to PuppyPi. Never invent sources, APIs, releases or results.
- Record what is actually reused: paper/source URL, repository revision or
  framework version, component, local adapter, execution command and observed
  result. A bibliography, candidate list, installed package or unused import is
  not implementation reuse or evidence that a feature works.
- Use the selected upstream implementation/framework in the supported execution
  path. Project-owned code should connect, configure and extend verified
  components; document any necessary custom algorithm and its limitations before
  presenting it as the chosen solution. A declared heuristic remains allowed,
  but cannot fulfill a claim of model inference or paper-repository integration.
- Exercise the genuine upstream example and the project integration before
  claiming success. Missing code, incompatible inputs, unavailable weights or
  execution failures must be reported as FAIL for the affected capability, with
  no hardcoded or fallback substitute. Keep source availability, installation,
  successful execution and evaluated quality as separate evidence states.

## Visible implementation disclosure

- Disclose the actual method at its point of use in the app, API and exports:
  custom Python/OpenCV/NumPy heuristic, human assertion, authored script/fixture,
  actual learned inference, or actual upstream implementation reuse. A research
  citation or installed framework never upgrades a custom baseline's status.
- Label every generated authored storyboard frame. Never display authored
  identity, score, motion or success as an inferred/measured result. Preserve
  historical artifacts with a prominent correction instead of rewriting evidence.
- Unknown backend names and required-model failures must raise errors; never
  select a baseline implicitly. Keep unknown angles/poses unknown rather than
  inventing coordinates. Report logical graph bookkeeping separately from motion.
- Keep method/configuration inventory separate from per-run execution evidence.
  Checked citation membership is not independently verified factual correctness.
  Consult `docs/review/2026-11-01-code-integrity-audit.md` before capability claims.

## Architecture and configuration

- Keep the Python core independent of ROS, model transport, and UI frameworks.
  Convert vendor/model output into project-owned records at adapter boundaries.
- Put operational defaults in `teach_and_find/config.py`. Configure model names,
  devices, endpoints, and deployment paths through Settings/environment values.
- Reuse existing interfaces before adding new frameworks or abstractions. Keep
  historical deterministic baselines available only as explicitly selected test
  or comparison paths. A model required by a promised capability is mandatory
  for that capability; an offline baseline must never substitute for it.
- Separate observations, derived beliefs, proposed actions, and measured action
  results. Timestamp captured evidence and preserve its provenance.
- Multi-camera evidence must retain camera/session identity, capture clock
  uncertainty, and calibration revision. Arrival time alone is not synchronization.
- Use explicit schema versions and migrations when durable storage is added.
  Never silently reinterpret stored embeddings from another model/preprocessor.
- Preserve vendor source assets, historical experiment records, and handoffs.
  Add corrections in current status documents instead of rewriting old evidence.

## Recorded-memory worker

- The supported Mind Palace app profile is recorded-memory question answering;
  use the actual pinned upstream through `MindPalaceAdapter`, never the legacy
  appearance baseline or operator assertions as an inference substitute.
- Prepare the optional source/environment with `make memory-setup`; run paid
  inference only in the separate `make memory-worker` process. The host app uses
  `.venv-dev/`, the optional worker uses `.venv-memory/`; preserve `.venv/`.
- Keep local visual-target checking separate from global answer readiness. Sparse
  recorded captures cannot establish current state, continuous coverage, exact
  identity, autonomous navigation or a learned predictive world model.
- `scripts/research_memory_app.py --allow-paid-api` is an explicitly opt-in,
  synthetic acceptance experiment, never a default test or physical robot demo.
  Consult `docs/22-mind-palace-app.md` and its actual execution report before
  promoting this profile's status or claiming a research advantage.

## Visual perception worker

- The optional app vision profile requires the pinned YOLOE author SAVPE model,
  the original DINOv2 ViT-S/14 backbone and the Ultralytics ByteTrack implementation
  distributed in the YOLOE source. Both learned models must execute; no YOLOE-only
  output may substitute for a required descriptor failure. Use `make vision-setup` and the separate `.venv-vision` CPU
  worker. Preserve the other environments; do not import its models into the
  camera/control worker or install both OpenCV wheel variants in one environment.
- Consult `docs/24-yoloe-vision.md` and the actual app execution report. A completed
  inference job is not a passed identity-quality gate. Keep raw false positives,
  missed detections and conflicting prompt labels visible; never correct them
  with simulator truth or an undisclosed marker/background blacklist.
- Rendered references and scenes are explicitly authored test inputs. Evaluator
  object identities, boxes and trajectories must not enter inference. Record
  source/checkpoint hashes and executed upstream calls separately from inventory.
- The user accepted the combined YOLOE → DINOv2 comparison → ByteTrack design.
  The comparison's maximum cosine/margin rule is explicitly custom, hand-selected
  decision logic, not a calibrated probability or an upstream identity classifier.
  Preserve raw/rejected proposals, per-reference cosines and false accepts/misses.
  A supported candidate is not confirmed identity, presence or current location.
- New vision jobs require explicit profile version 2; do not reinterpret older
  queued jobs or legacy descriptors. Check the DINOv2 loader cache digest as well
  as the original checkpoint. The research-only probe is distinct from the actual
  production adapter and per-run combined-model evidence.

## Interactive tracking component evidence

- Consult `docs/26-interactive-target-tracking.md`, the current
  `docs/28-live-stream-scheduling.md`, and actual
  `docs/research/2026-11-02-tracking-freshness/report.md` before tracking claims.
  Original SAM 2.1/Cutie app selection, preview and future-frame inference ran on
  CPU over rendered input. Profile-v2 latest-frame scheduling produced 292
  observations over 120 seconds with bounded pending work. The full 5 FPS gate,
  held-out identity/segmentation quality, Find-again/recovery and physical
  acceptance remain unpassed. The older component report is historical evidence,
  not a reason to call this delivered subset unimplemented or the full feature done.
- The opt-in component environment is `.venv-tracking/`; preserve the other
  environments. CPU runs must hide CUDA before CUDA discovery: the original SAM
  constructor can otherwise warm a GPU cache despite a CPU model request.
  An explicitly requested CUDA run must fail on device/memory failure, never
  retry on CPU implicitly. The recorded CUDA OOM is a free-VRAM failure, not proof
  that this machine lacks GPU hardware or that CPU execution is impossible.

## Calibrated search completion work

- The opt-in search path is documented in `docs/29-complete-teach-search-memory.md`.
  Its four-view navigation/model jobs execute, but identity acceptance is **FAIL**:
  experimental readouts include positives, inconclusive cases and a false
  confirmation. Do not describe the requested end-to-end feature as complete.
- Keep `SearchSettings.quality_qualified=False` until a frozen positive, negative,
  ambiguity and failure evaluation passes with recorded evidence. Never toggle it
  merely to allow automatic-memory publication or make a demonstration pass.
- On 2026-11-02 the user explicitly accepted revised model roles: YOLOE proposes
  regions, DINOv2 supplies gallery identity, DISK/LightGlue verifies geometric
  correspondences across views. New search payload v2 uses vision profile v3.
  Preserve original vision profile v2 and historical failures; never reinterpret
  them as the revised method. See the detailed identity-gate case in docs/review.
- Search transport uses separate latest-only status/camera slots and an independent
  leased sender. Camera HTTP, model inference or a stalled producer must never
  create a motion queue, renew stale movement, or automatically rearm.
- The search renderer owns truth only for evaluation. Navigation consumes observed
  tag pixels plus supplied map/calibration, never renderer pose or object labels.

## Robot execution

- Do not hold a navigation motion lease across heavy model initialization or
  stationary inference. In the calibrated search profile, end each navigation
  segment with acknowledged zero-command/disarm, require an image captured after
  that acknowledgement, then close its control transport before inference.
  New segments must validate the running task's runtime motion-generation token,
  fresh same-session camera and calibration. Planned segment completion is
  distinct from fault recovery: Stop, unexpected expiry/disconnect, invalid
  commands or restart revoke authority; never automatically rearm after them.
  Adapter acknowledgement does not establish measured physical stopping.

- Physical actuation must be within the user's authorized task. Default tests
  use synthetic frames and loopback transports, never a discovered live robot.
- Preserve robot-side stop/watchdog behavior and bounded movement commands.
  Inference delays, stale frames, and reconnections must not perpetuate motion.
- Keep language-model outputs behind validated task/skill contracts. Do not
  execute arbitrary model-generated code or motor commands.
- Treat vendor source limits as assumptions until verified on the actual kit.
  Test feasible movement, units, camera calibration, and pose feedback before
  claiming physical capability. AprilTags do not provide obstacle avoidance.
- Stop project-owned mock servers and background processes after tests, including
  failures. Do not stop unrelated services or remove user environments/data.

## Research integrity and feature status

- Remember the 2026-11-02 [identity-role counterexample](docs/review/2026-11-02-yoloe-identity-gate-case.md):
  removing the YOLOE-label veto recovered a real candidate, but DINOv2 plus
  DISK/LightGlue still falsely confirmed an unknown object with an identical
  front and different sides. Shared-surface correspondences, multiple camera
  views and gallery-image coverage do not prove matching distinguishing surfaces
  or complete identity. Preserve this failed case; do not tune on it and report
  the revised threshold as held-out success. Keep automatic-memory publication
  blocked until the agreed quality acceptance actually passes.

- **FATAL / CRITICAL / LETHAL: capability integrity is a mandatory acceptance gate.**
  Implement and demonstrate the capability as described. If the promised path
  cannot run, mark it FAIL and report the actual error and missing component.
  Passing UI/unit tests, attractive screenshots, or a proposal cannot override FAIL.
- No hardcoded answers, identities, world states, simulator truth, scripted motion,
  or operator annotations may substitute for a promised automatic capability.
  Synthetic fixtures are allowed only in explicitly labeled tests/comparisons;
  they do not establish perception, navigation, learned control, or research integration.
- No fallback for the promised capability: do not substitute mock data, heuristics,
  another backend, manual confirmation, or canned output when its required model,
  upstream implementation, checkpoint, dependency, endpoint, or input is unavailable.
  Stop that capability and expose failure; preserve independent robot stop behavior.
- A heuristic solution is allowed when declared as heuristic from the outset,
  with its scope and assumptions agreed in the task description. Do not replace
  a promised AI/model/research implementation with a heuristic or relabel one later.
  Do not silently downgrade any agreed method, including a heuristic method.
- If claiming AI/model inference, identify the actual model, weights/version,
  preprocessing, invoked entry point, input/output, and observed execution evidence.
  An unused adapter or dependency is not integrated inference. A vision model is
  not automatically a world model, and object matching is not autonomous navigation.
- If describing a feature as based on or integrated from a research repository,
  actually use that repository's relevant implementation in the supported path.
  Record upstream URL, revision, license, reused files/components, modifications,
  execution command, and evidence. A citation, reimplementation of an idea, or
  similarly named class is insufficient; label inspiration/reimplementation explicitly.
- Before reporting completion, trace real input through the claimed implementation
  to the user-visible result, distinguish model/algorithm output from human labels
  and simulator truth, and test missing-dependency/model failure. Report software,
  algorithm-quality, simulation, and physical evidence separately. Never prepare
  academic progress claims that exceed this evidence.
- Distinguish Planned, Prototype, Integrated, and Hardware verified. Update the
  feature inventory with the implementation and evidence when status changes.
- A planned API, a mock, or a scripted animation is not a delivered robot feature.
  Synthetic, replay, physics, and physical results must be labeled separately.
- Similarity and heuristic confidence scores are not calibrated probabilities.
  Support calibration and novelty claims with explicit evaluation and sources.
- Keep baselines comparable: same perception/model versions, paired scenes,
  budgets, and leakage-free evaluation splits. Count failures/interventions.
- Reuse papers, code, and checkpoints with recorded provenance. Verify actual
  code availability and input assumptions before promising an integration.
- Do not commit credentials, downloaded weights, private recordings, or complete
  camera streams. Use ignored `data/`, `recordings/`, and `runs/` directories.

## Verification and commits

- Use `make setup` and the isolated `.venv-dev/`; preserve an existing `.venv/`.
- Prefix direct `uv` project commands with `UV_PROJECT_ENVIRONMENT=.venv-dev`;
  Make's exported setting does not persist into later shell commands.
- Run `make check`, `make test`, and `make build` for code/dependency/workflow
  changes. Documentation-only changes require `make check`. State any unrun
  relevant hardware or optional GPU checks honestly.
- For mobile UI changes, also run `make app-build` and `make app-test`; inspect
  desktop and phone screenshots. Browser tests must use the disposable synthetic
  server. Never cache camera/evidence API responses or queue motion offline.
- Default tests must not download models, call paid APIs, require ROS/GPU, or
  actuate hardware. Add regression tests for meaningful behavior and failure
  handling; do not add tests that merely mirror trivial implementation details.
- Use the commit format and scopes in `CONTRIBUTING.md`; enable `make hooks`.
  Commit coherent, reviewable slices with their tests and relevant documentation.
- Stage explicit paths and inspect the staged diff. Use `docs(...)` for a plan;
  use `feat(...)` for implemented behavior. Do not pad history with empty commits.
- Preserve others' changes. Do not amend, rebase, force-push, publish, or configure
  a remote unless the task authorizes it. Repository initialization alone is local.
- For substantial work, write `docs/handoffs/YYYY-MM-DD-handoff.md` with completed
  work, evidence, unresolved constraints, and the next concrete implementation step.
