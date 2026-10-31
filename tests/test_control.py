"""Manual motion requires a live, exclusive, replay-resistant lease."""

import math

import pytest

from teach_and_find.config import Settings
from teach_and_find.control import ControlGate
from teach_and_find.storage import AssistantError


def test_lease_expiry_and_stop_reject_old_session_and_queued_arm():
    now = [0.0]
    gate = ControlGate(Settings(), lambda: now[0])
    challenge = gate.challenge()
    epoch = gate.arm("alice", challenge, ready=True)
    assert gate.drive("alice", epoch, 1, challenge, 0.5, 0, ready=True).vx_cm_s == 3
    now[0] = 0.46
    assert gate.tick(ready=True).vx_cm_s == 0
    assert gate.reason == "command_expired"
    with pytest.raises(AssistantError, match="Arm a new"):
        gate.drive("alice", epoch, 2, gate.challenge(), 1, 0, ready=True)
    challenge = gate.challenge()
    gate.stop()
    with pytest.raises(AssistantError, match="expired"):
        gate.arm("alice", challenge, ready=True)


def test_exclusive_owner_and_repeated_sequence_disarm():
    gate = ControlGate(Settings())
    challenge = gate.challenge()
    epoch = gate.arm("alice", challenge, ready=True)
    with pytest.raises(AssistantError, match="already active"):
        gate.arm("bob", challenge, ready=True)
    gate.disconnect("bob")
    assert gate.owner == "alice"
    gate.drive("alice", epoch, 1, challenge, 1, -1, ready=True)
    with pytest.raises(AssistantError, match="repeated"):
        gate.drive("alice", epoch, 1, challenge, 1, -1, ready=True)
    assert gate.owner is None and gate.command.vx_cm_s == 0


@pytest.mark.parametrize("value", [math.nan, math.inf, -1.1, 1.1])
def test_invalid_motion_never_reaches_execution(value):
    gate = ControlGate(Settings())
    challenge = gate.challenge()
    epoch = gate.arm("alice", challenge, ready=True)
    with pytest.raises(AssistantError):
        gate.drive("alice", epoch, 0, challenge, value, 0, ready=True)
    assert gate.owner is None and gate.command.vx_cm_s == 0


def test_camera_loss_and_expired_challenge_stop_even_with_recent_lease():
    now = [0.0]
    gate = ControlGate(Settings(), lambda: now[0])
    old = gate.challenge()
    epoch = gate.arm("alice", old, ready=True)
    now[0] = 0.3
    gate.drive("alice", epoch, 0, gate.challenge(), 1, 0, ready=True)
    now[0] = 0.5
    with pytest.raises(AssistantError, match="Delayed"):
        gate.drive("alice", epoch, 1, old, 1, 0, ready=True)
    epoch = gate.arm("alice", gate.challenge(), ready=True)
    gate.drive("alice", epoch, 0, gate.challenge(), 1, 0, ready=True)
    assert gate.tick(ready=False).vx_cm_s == 0
    assert gate.owner is None
