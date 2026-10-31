"""Project-owned camera evidence records, independent of transport and UI."""

from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np


@dataclass(frozen=True)
class CameraFrame:
    image: np.ndarray
    frame_id: str
    captured_at: str
    received_monotonic: float
    age_at_receipt_s: float
    freshness_verified: bool
    provenance: dict

    def age(self, now: float | None = None) -> float:
        return self.age_at_receipt_s + max(
            0.0, (time.monotonic() if now is None else now) - self.received_monotonic
        )
