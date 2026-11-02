"""Loopback-only simulator host; optional evaluator trace never reaches control."""

import json
import os
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from teach_and_find.config import Settings
from teach_and_find.mobile.api import create_app
from teach_and_find.mobile.runtime import OperatorRuntime


class PhoneRuntime(OperatorRuntime):
    """Flush evaluator data inside app shutdown, before Uvicorn re-raises SIGTERM."""

    def __init__(self, cfg, trace):
        super().__init__(cfg)
        self.trace = trace
        self.device.evaluation_enabled = bool(trace)

    def close(self):
        super().close()
        if self.trace:
            Path(self.trace).write_text(
                json.dumps(
                    {
                        "scope": "evaluator-only kinematic integration/capture trace; no ROS or physics",
                        "trajectory": list(self.device.evaluation_trajectory),
                        "frames": list(self.device.evaluation_frames),
                    },
                    indent=2,
                )
            )


def main():
    import uvicorn

    cfg = Settings()
    cfg = replace(cfg, mobile=replace(cfg.mobile, robot_mode="search-sim"))
    runtime = PhoneRuntime(cfg, os.getenv("PUPPYPI_PHONE_TRACE"))
    uvicorn.run(
        create_app(cfg, runtime=runtime),
        host="127.0.0.1",
        port=int(os.environ["PUPPYPI_PHONE_PORT"]),
        access_log=False,
    )


if __name__ == "__main__":
    main()
