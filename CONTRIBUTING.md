# Contributing to PuppyPi

Build reviewable features on the shared Teach and Find core. Start with the
[status](docs/00-project-status.md), [roadmap](docs/06-feature-roadmap.md), and
[agent instructions](AGENTS.md). This repository has its own `.git/`; the parent
ECUS repository is outside the scope of normal work here.

## Environment and checks

Use Python 3.12 and `uv`. The default development environment is `.venv-dev/`.

```bash
make setup
make hooks
make check
make test
make build
```

`make check` runs focused Ruff correctness rules, local Markdown target checks,
commit-title validation, and Git whitespace checks on current changes. It is not
a type checker or a full style audit. `make test` runs the synthetic and mock
relay suite. `make build` creates a wheel and source distribution under ignored
`dist/`. For ad hoc project commands, explicitly prefix
`UV_PROJECT_ENVIRONMENT=.venv-dev uv run ...`; Make's exported environment does
not persist into a later shell. Avoid accidentally syncing an existing `.venv/`.
The Python core needs no Node runtime. The optional mobile console has
a frontend build under `web/` and uses Node 22.12+ (Node 24 tested):

```bash
make app-setup
make app-build
npm --prefix web exec -- playwright install chromium
make app-test
```

Run the app build and browser tests for UI changes, alongside the Python checks.
`make app-build` typechecks TypeScript and writes ignored static assets under
`teach_and_find/mobile/static/`. Build those assets before `make build` when
shipping an app-enabled wheel. A core-only wheel without them still supports the
CLI; its HTTP root explains that the frontend needs building. Browser tests own
a temporary database and a loopback-only synthetic server and stop it on exit.
Do not use a real relay in automated browser tests.

`make setup-sim` installs optional MuJoCo dependencies. `make render-3d` uses EGL
and requires a compatible graphics environment. The source-distribution/wheel
contains the Python package; visualization scripts and CAD files require a full
repository checkout.

Keep `pyproject.toml` and `uv.lock` in the same dependency-change commit. Run
`uv lock` after changing dependency declarations. GPU/ROS deployment stacks are
separate opt-in integrations; do not add them to the default test dependencies.

## Commit convention

Use scoped Conventional Commit titles:

```text
<type>(<scope>): <imperative English description>
<type>(<scope>)!: <description of a breaking change>
```

The first line must be at most 72 characters, with a lowercase initial description
and no final period. Use a concrete verb such as `add`, `fix`, `preserve`, or
`document`. The hook validates structure, scope, length, initial case, and final
punctuation; reviewers check meaning and imperative wording.

| Type | Use |
| --- | --- |
| `feat` | Implemented capability or imported working baseline |
| `fix` | Correct behavior or a regression |
| `docs` | Documentation, research plan, or handoff |
| `refactor` | Internal change without intended behavior change |
| `test` | Regression tests, test fixtures, or evaluation assertions |
| `perf` | Measured performance improvement |
| `build` | Dependencies, packaging, or build configuration |
| `ci` | Automated integration checks |
| `chore` | Repository maintenance or development tooling |
| `revert` | A deliberate reversal, with the original revision in the body |

Allowed scopes: `repo`, `core`, `perception`, `memory`, `planner`, `verification`,
`mission`, `inspection`, `interaction`, `motion`, `bridge`, `sim`, `eval`, `ui`,
`research`, `docs`, `deps`, `workflow`, `tests`, `assets`.

Examples:

```text
feat(memory): persist timestamped object sightings
fix(bridge): reject commands after their deadline
test(verification): cover absent targets and look-alike objects
docs(research): define memory freshness ablations
build(deps): pin optional simulator dependencies
```

For nontrivial changes, explain the problem, observable behavior, and validation
in the body. Reference feature IDs where relevant:

```text
feat(memory): persist timestamped object sightings

Keep confirmed observations across restarts so the operator can query
the last observed location with its source image and capture time.

Features: F10, F11
Validation: make check; make test; make build
Hardware: not exercised; persistence-only change
```

Breaking changes need an explanation and migration instructions in a
`BREAKING CHANGE:` footer. Commit related tests and documentation with the code.
Do not create separate commits solely to reach a target count. A roadmap update
uses `docs`, even when it describes future features.

## Local hook and history

`make hooks` configures `core.hooksPath=.githooks` in this repository only. New
clones must run it once. The `commit-msg` hook requires `python3`, not the project
environment. Check all existing commit titles with:

```bash
python3 scripts/check_commit_message.py --history
```

All commits, including merges and reverts, need a conforming subject. Use
`git merge --no-commit` and supply a valid message, or squash a branch with a
conforming title. Avoid leaving `fixup!`/`squash!` commits in the final history.
Check titles before a commit rather than bypassing the hook.

Use focused branches when helpful, for example
`feat/memory-f11-sightings` or `fix/bridge-command-expiry`. Stage explicit paths
and review `git diff --cached`. Do not include another feature's experiments,
private camera frames, cached models, or local settings in the same commit.

## Feature and research completion

Every promoted feature needs a supported entry point, one successful scenario,
one relevant failure scenario, and evidence appropriate to its status. Update
the roadmap and status page together when capabilities change. Research changes
also need comparable baselines and a reproducible run manifest as described in
[the research program](docs/07-research-program.md) and
[demo acceptance](docs/09-demo-acceptance.md).

Preserve original handoffs and baseline artifacts. New physical recordings stay
in ignored directories until selected evidence is intentionally prepared for
sharing. Record third-party provenance before importing new assets or code.
