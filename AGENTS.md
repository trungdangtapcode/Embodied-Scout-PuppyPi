# PuppyPi repository instructions

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

## Robot execution

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
