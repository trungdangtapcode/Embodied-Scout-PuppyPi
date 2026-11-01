"""Pure temporal scheduling and a bounded latest-value producer mailbox.

These are custom operational policies, not learned tracking or a GStreamer
integration. Model inference remains the original SAM/Cutie implementation.
"""

from dataclasses import dataclass
import threading

from teach_and_find.errors import AssistantError


class LatestMailbox:
    """One waiting value; producers replace old waiting work without blocking.

    The consumer owns a taken value independently. Closing wakes waiters and
    discards pending work. The cumulative replacement count is lock protected.
    """

    def __init__(self):
        self._condition = threading.Condition()
        self._pending = None
        self._closed = False
        self._replacements = 0

    def offer(self, value):
        with self._condition:
            if self._closed:
                return False
            if self._pending is not None:
                self._replacements += 1
            self._pending = value
            self._condition.notify()
            return True

    def take(self):
        with self._condition:
            self._condition.wait_for(lambda: self._closed or self._pending is not None)
            if self._closed:
                return None
            value, self._pending = self._pending, None
            return value

    def snapshot(self):
        with self._condition:
            return {
                "pending": int(self._pending is not None),
                "replacements": self._replacements,
            }

    def close(self):
        with self._condition:
            self._closed = True
            self._pending = None
            self._condition.notify_all()


@dataclass(frozen=True)
class ScheduledFrame:
    sequence: int
    record: dict
    was_head: bool
    skipped: int
    phase: str


def select_frame(
    frames, *, phase, previous_sequence, previous_capture, now, max_gap, max_age
):
    """Bootstrap advances within a bounded gap; live always chooses the head.

    ``frames`` is an immutable ordered repository snapshot of (sequence, record).
    No frame or mask is synthesized. Oversized temporal gaps fail, not rewind.
    """
    candidates = [(seq, record) for seq, record in frames if seq > previous_sequence]
    if not candidates:
        if previous_capture is not None and now - previous_capture > max_gap:
            raise AssistantError("TRACKING_FRAME_GAP", "No timely next source frame.")
        return None
    if phase not in ("bootstrap", "live"):
        raise AssistantError(
            "TRACKING_PHASE_INVALID", "Unknown temporal scheduling phase."
        )
    head = candidates[-1]
    if phase == "bootstrap":
        reachable = [
            (seq, record)
            for seq, record in candidates
            if 0 < record["capture_unix_ms"] / 1000 - previous_capture <= max_gap
        ]
        if not reachable:
            raise AssistantError(
                "TRACKING_FRAME_GAP",
                "No retained bootstrap source within the temporal gap.",
            )
        selected = reachable[-1]
    else:
        selected = head
    seq, record = selected
    capture = record["capture_unix_ms"] / 1000
    if previous_capture is not None and not 0 < capture - previous_capture <= max_gap:
        raise AssistantError(
            "TRACKING_FRAME_GAP",
            "Newest source violates the temporal gap; no historical substitute.",
        )
    if phase == "live" and now - capture > max_age:
        raise AssistantError(
            "TRACKING_INPUT_STALE", "Newest live source has already expired."
        )
    return ScheduledFrame(
        seq, record, seq == head[0], seq - previous_sequence - 1, phase
    )
