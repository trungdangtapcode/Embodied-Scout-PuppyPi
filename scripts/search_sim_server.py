"""Explicit disposable simulator host, with truth logged for evaluation only."""

import argparse
from dataclasses import replace
import json
from pathlib import Path

import uvicorn

from teach_and_find.config import Settings
from teach_and_find.mobile.api import create_app
from teach_and_find.mobile.runtime import OperatorRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=18784)
    args = parser.parse_args()
    cfg = Settings()
    cfg = replace(cfg, mobile=replace(cfg.mobile, robot_mode="search-sim"))
    runtime = OperatorRuntime(cfg)
    runtime.device.evaluation_enabled = True
    try:
        uvicorn.run(
            create_app(cfg, runtime=runtime),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
        )
    finally:
        Path(args.output).write_text(
            json.dumps(
                {
                    "source": "renderer_truth_evaluation_only_never_controller_input",
                    "trajectory": list(runtime.device.evaluation_trajectory),
                    "frames": list(runtime.device.evaluation_frames),
                    "collisions": runtime.device.evaluation_collisions,
                    "collision_measurement": getattr(
                        runtime.device, "evaluation_collision_method", None
                    ),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
