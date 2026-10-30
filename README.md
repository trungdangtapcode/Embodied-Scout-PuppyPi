# PuppyPi Research Assistant

An application and R&D platform for **Hiwonder PuppyPi**, built on the existing
**Teach and Find** Python core. The roadmap combines object search, temporal
memory, interactive clarification, workspace inspection, and active vision.

## Current capability

The repository contains a software prototype for synthetic few-shot object
search, multi-view verification, topological planning, AprilTag recovery, and a
ROS 2/TCP bridge with a tested loopback watchdog. It also includes synthetic
experiment artifacts and MuJoCo CAD visualizations.

The expanded applications are **planned**, not already implemented. Physical
robot validation is pending. Historical benchmark scores describe the supplied
synthetic scenario. Read [capability and evidence status](docs/00-project-status.md).

## Application and research tracks

| Track | Intended application | Research question |
| --- | --- | --- |
| Memory Scout | Remember and find objects after they move | When should old observations be checked again? |
| Look-or-Ask | Resolve ambiguity through a view or question | How should information, movement and human effort be traded off? |
| Inspect and Explain | Check presence, placement and visible states | Which observations distinguish meaningful changes from nuisances? |
| Body-aware Active Vision | Change pose or wait for a stable image | Which feasible action improves recognition per unit time? |

The [32-feature inventory](docs/06-feature-roadmap.md) records status, priority,
dependencies, and acceptance criteria. Features share one perception, evidence,
mission, and motion stack.

## Quick start

Python 3.12 is the reference interpreter. Install `uv` and run from this directory:

```bash
make setup
make check
make test
make build
make hooks
```

Commands use `.venv-dev/`, preserving an existing `.venv/`. `uv.lock` pins core,
development, and optional simulator dependencies. Default tests use synthetic
images and a loopback relay; they do not actuate hardware or invoke paid APIs.
ROS 2 and pretrained GPU models are optional deployment integrations.

```bash
make benchmark       # synthetic experiment; updates tracked outputs
make render-3d       # optional MuJoCo EGL visualization with sim extras
make tags            # regenerate printable AprilTags
```

The renderer regenerates ignored `assets/mujoco_generated/` for the checkout path.
Inspect output changes before committing a new benchmark.

## Project map

- `teach_and_find/`: perception, memory, planning, missions, adapters, simulation.
- `scripts/`: experiments, visualization, marker generation, relay, checks.
- `tests/`: software and mock-relay regressions.
- `assets/`: CAD snapshot with [provenance notes](assets/README.md).
- `outputs/`: reviewed [historical synthetic evidence](outputs/README.md).
- `docs/`: status, feature roadmap, research, architecture, acceptance.

Start with [the documentation index](docs/README.md),
[the research program](docs/07-research-program.md), and
[the shared architecture](docs/08-system-evolution.md).
See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) for development
and commit rules.

This directory is its own Git repository, independent of the surrounding ECUS
repository. The bootstrap configures no remote. Source assets retain their
original ownership and terms.
