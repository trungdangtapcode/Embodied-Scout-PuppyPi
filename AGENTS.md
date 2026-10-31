# PuppyPi repository instructions

## Scope and priorities

- This is the standalone PuppyPi repository rooted at this directory. Check
  `git rev-parse --show-toplevel` before Git operations; do not edit or commit
  the surrounding ECUS project as part of PuppyPi work.
- Read `docs/00-project-status.md`, `docs/06-feature-roadmap.md`, and the relevant
  research track before changing behavior. Prioritize working application
  features with observable acceptance criteria and reusable research components.
- Share perception, evidence, task state, and motion execution across Memory
  Scout, Look-or-Ask, Inspect and Explain, Body-aware Active Vision, and Phone Observer.
- Keep source identifiers, comments, commit messages, and technical documents in
  English. Communicate with the user in their preferred language.

## Architecture and configuration

- Keep the Python core independent of ROS, model transport, and UI frameworks.
  Convert vendor/model output into project-owned records at adapter boundaries.
- Put operational defaults in `teach_and_find/config.py`. Configure model names,
  devices, endpoints, and deployment paths through Settings/environment values.
- Reuse existing interfaces before adding new frameworks or abstractions. Keep
  pretrained backbones optional and the deterministic offline baseline usable.
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
