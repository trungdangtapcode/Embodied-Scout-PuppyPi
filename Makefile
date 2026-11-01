UV_PROJECT_ENVIRONMENT ?= .venv-dev
export UV_PROJECT_ENVIRONMENT
UV_RUN = uv run --locked --extra dev

.PHONY: setup setup-sim hooks check test build benchmark render-3d tags demo-assistant app-setup app-build app app-test

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

demo-assistant:
	$(UV_RUN) python scripts/demo_assistant.py

app-setup:
	uv sync --locked --extra dev --extra app
	npm --prefix web ci

app-build:
	npm --prefix web run build

app:
	$(UV_RUN) --extra app python -m teach_and_find.mobile $(APP_ARGS)

app-test:
	npm --prefix web test

.PHONY: memory-setup memory-worker
memory-setup:
	UV_PROJECT_ENVIRONMENT=.venv-memory uv sync --locked --extra memory
	UV_PROJECT_ENVIRONMENT=.venv-memory uv run --locked --extra memory python scripts/setup_memory_upstream.py

memory-worker:
	PUPPYPI_MEMORY_ENABLED=1 UV_PROJECT_ENVIRONMENT=.venv-memory uv run --locked --extra memory python -m teach_and_find.memory_worker

.PHONY: vision-setup vision-worker
vision-setup:
	$(UV_RUN) python scripts/setup_vision.py

vision-worker:
	PUPPYPI_VISION_ENABLED=1 CUDA_VISIBLE_DEVICES=-1 PYTHONPATH=. .venv-vision/bin/python -m teach_and_find.vision_worker
