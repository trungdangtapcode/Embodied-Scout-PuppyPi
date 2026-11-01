"""Disposable loopback-only synthetic server for Playwright; never uses user data."""

from dataclasses import replace
import tempfile

import uvicorn

from teach_and_find.config import Settings
from teach_and_find.mobile.api import create_app


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="puppypi-browser-") as directory:
        cfg = Settings()
        cfg = replace(
            cfg,
            assistant=replace(cfg.assistant, data_dir=directory),
            memory=replace(cfg.memory, enabled=True),
            vision=replace(cfg.vision, enabled=True),
            tracking=replace(cfg.tracking, enabled=True),
            mobile=replace(
                cfg.mobile,
                robot_mode="mock",
                allow_physical_motion=False,
                pairing_token="synthetic-browser-test",
            ),
        )
        uvicorn.run(create_app(cfg), host="127.0.0.1", port=18766, access_log=False)
