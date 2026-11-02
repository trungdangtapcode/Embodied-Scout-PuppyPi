"""Camera producer timing with explicit synthetic work/clock, no models or robot."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import utc_now
from teach_and_find.mobile.runtime import OperatorRuntime
import teach_and_find.mobile.runtime as runtime_module


def test_camera_work_counts_towards_cadence_and_overrun_does_not_queue(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    starts, work = [], [0.08, 0.08, 0.35, 0.08, 0.08]

    class Device:
        mode = "synthetic"

        def read_frame(self):
            starts.append(clock.now)
            clock.now += work[len(starts) - 1]
            return CameraFrame(
                np.zeros((32, 32, 3), np.uint8),
                str(len(starts)),
                utc_now(),
                clock.now,
                0,
                True,
                {"camera_id": "unit-fixture"},
            )

    class Stop:
        def __init__(self):
            self.calls = 0

        def is_set(self):
            return self.calls == len(work)

        def wait(self, duration):
            clock.now += duration
            self.calls += 1

    cfg = Settings()
    cfg = replace(cfg, mobile=replace(cfg.mobile, frame_poll_s=0.1))
    runtime = OperatorRuntime(cfg, Device())
    runtime.stop_event = Stop()
    monkeypatch.setattr(
        runtime_module, "time", SimpleNamespace(monotonic=lambda: clock.now)
    )
    runtime._camera_loop()
    assert starts == pytest.approx([0, 0.1, 0.2, 0.55, 0.65])
    assert runtime.latest.frame_id == "5"
    assert runtime.gate.owner is None
