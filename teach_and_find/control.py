"""Transport-independent manual control lease with explicit stop and expiry."""

from __future__ import annotations

from collections import deque
import math
import secrets
import time
from typing import Callable

from teach_and_find.config import Settings
from teach_and_find.mission import PuppyActionCommand
from teach_and_find.storage import AssistantError


class ControlGate:
    """One operator at a time; fresh challenges prevent replaying queued motion.

    The runtime serializes calls under its lock. This class never opens a network
    connection and never claims that a command is a measured movement.
    """

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.monotonic):
        self.settings = settings
        self.clock = clock
        self.owner: str | None = None
        self.epoch: str | None = None
        self.sequence = -1
        self.expires_at = 0.0
        self.command = PuppyActionCommand.clamped(settings.motion)
        self.reason = "disarmed"
        self.challenges: deque[tuple[str, float]] = deque(maxlen=32)

    def challenge(self) -> str:
        now = self.clock()
        if (
            not self.challenges
            or now - self.challenges[-1][1] >= self.settings.mobile.control_tick_s
        ):
            self.challenges.append((secrets.token_urlsafe(12), now))
        return self.challenges[-1][0]

    def _fresh(self, challenge: str) -> bool:
        return any(
            token == challenge
            and self.clock() - issued <= self.settings.mobile.control_challenge_s
            for token, issued in self.challenges
        )

    def arm(self, owner: str, challenge: str, *, ready: bool) -> str:
        self.tick(ready=ready)
        if not ready:
            raise AssistantError(
                "CONTROL_UNAVAILABLE",
                "A fresh camera and an enabled robot connection are required.",
            )
        if not self._fresh(challenge):
            raise AssistantError(
                "STALE_CONTROL", "Control status expired. Wait for a fresh update."
            )
        if self.owner is not None:
            raise AssistantError("CONTROL_BUSY", "A control session is already active.")
        self.owner = owner
        self.epoch = secrets.token_urlsafe(18)
        self.sequence = -1
        self.expires_at = self.clock() + self.settings.mobile.command_lease_s
        self.reason = "armed"
        return self.epoch

    def drive(
        self,
        owner: str,
        epoch: str,
        sequence: int,
        challenge: str,
        forward: float,
        turn: float,
        *,
        ready: bool,
    ) -> PuppyActionCommand:
        self.tick(ready=ready)
        if owner != self.owner or epoch != self.epoch or self.owner is None:
            raise AssistantError(
                "NOT_CONTROLLER", "Arm a new control session before driving."
            )
        if not self._fresh(challenge) or sequence <= self.sequence:
            self.stop("stale_command")
            raise AssistantError(
                "STALE_CONTROL",
                "Delayed or repeated motion was rejected; controls disarmed.",
            )
        if any(
            not math.isfinite(value) or not -1 <= value <= 1
            for value in (forward, turn)
        ):
            self.stop("invalid_command")
            raise AssistantError(
                "INVALID_MOTION", "Motion values must be finite numbers from -1 to 1."
            )
        self.sequence = sequence
        self.expires_at = self.clock() + self.settings.mobile.command_lease_s
        self.command = PuppyActionCommand.clamped(
            self.settings.motion,
            vx_cm_s=forward * self.settings.mobile.manual_speed_cm_s,
            yaw_rate_rad_s=turn * self.settings.mobile.manual_yaw_rate_rad_s,
            description="manual_operator",
        )
        self.reason = "moving" if forward or turn else "armed"
        return self.command

    def stop(self, reason: str = "operator_stop") -> None:
        self.owner = None
        self.epoch = None
        self.expires_at = 0.0
        self.command = PuppyActionCommand.clamped(self.settings.motion)
        self.reason = reason
        self.challenges.clear()

    def disconnect(self, owner: str) -> None:
        if owner == self.owner:
            self.stop("operator_disconnected")

    def tick(self, *, ready: bool) -> PuppyActionCommand:
        if self.owner is not None:
            if not ready:
                self.stop("camera_or_connection_lost")
            elif self.clock() >= self.expires_at:
                self.stop("command_expired")
        return self.command
