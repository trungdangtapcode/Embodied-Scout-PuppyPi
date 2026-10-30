UV_PROJECT_ENVIRONMENT ?= .venv-dev
export UV_PROJECT_ENVIRONMENT
UV_RUN = uv run --locked --extra dev

.PHONY: setup setup-sim hooks check test build benchmark render-3d tags

setup:
	uv sync --locked --extra dev

setup-sim:
	uv sync --locked --extra dev --extra sim

hooks:
	git config --local core.hooksPath .githooks

check:
	$(UV_RUN) ruff check teach_and_find scripts tests
	$(UV_RUN) python scripts/check_docs.py
	$(UV_RUN) python scripts/check_commit_message.py --history
	git diff --check
	git diff --cached --check

test:
	$(UV_RUN) python -m pytest

build:
	uv build

benchmark:
	$(UV_RUN) python scripts/run_experiments.py

render-3d:
	MUJOCO_GL=egl $(UV_RUN) --extra sim python scripts/render_3d_puppypi_sim.py

tags:
	$(UV_RUN) python scripts/print_apriltags.py
