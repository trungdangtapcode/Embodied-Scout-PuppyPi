"""Deterministic overload/race tests; no learned inference is claimed here."""

from dataclasses import replace
import json
import threading

import pytest

from teach_and_find.storage import AssistantError, EvidenceStore, MIGRATIONS
from teach_and_find.tracking_frames import FrameInbox
from teach_and_find.tracking_schedule import LatestMailbox, select_frame
from teach_and_find.tracking_service import TrackingService
from test_tracking import cfg, frame, ready  # Reuse explicit offline fixture.


def record(sequence, capture):
    return {"frame_id": f"fixture-{sequence}", "capture_unix_ms": capture * 1000}


def test_mailbox_replaces_old_waiting_work_and_close_wakes_consumer():
    mailbox = LatestMailbox()
    for value in range(10000):
        mailbox.offer(value)
    assert mailbox.snapshot() == {"pending": 1, "replacements": 9999}
    current = mailbox.take()
    for value in range(10000, 11000):
        mailbox.offer(value)
    assert current == 9999  # In-flight ownership is independent of new offers.
    assert mailbox.take() == 10999
    done = []
    waiting = threading.Thread(target=lambda: done.append(mailbox.take()))
    waiting.start()
    mailbox.close()
    waiting.join(timeout=1)
    assert not waiting.is_alive() and done == [None]
    assert mailbox.offer(11000) is False


def test_live_selects_newest_bootstrap_uses_bounded_temporal_hops():
    frames = [(i, record(i, i * 0.125)) for i in range(1, 21)]
    bootstrap = select_frame(
        frames,
        phase="bootstrap",
        previous_sequence=0,
        previous_capture=0,
        now=2.6,
        max_gap=0.6,
        max_age=1,
    )
    assert bootstrap.sequence == 4 and bootstrap.skipped == 3
    assert not bootstrap.was_head
    live = select_frame(
        frames[-4:],
        phase="live",
        previous_sequence=16,
        previous_capture=2,
        now=2.6,
        max_gap=0.6,
        max_age=1,
    )
    assert live.sequence == 20 and live.was_head and live.skipped == 3
    with pytest.raises(AssistantError) as exc:
        select_frame(
            frames,
            phase="live",
            previous_sequence=0,
            previous_capture=0,
            now=2.6,
            max_gap=0.6,
            max_age=1,
        )
    assert exc.value.code == "TRACKING_FRAME_GAP"
    with pytest.raises(AssistantError) as exc:
        select_frame(
            frames[-4:],
            phase="live",
            previous_sequence=16,
            previous_capture=2,
            now=3.6,
            max_gap=0.6,
            max_age=1,
        )
    assert exc.value.code == "TRACKING_INPUT_STALE"


def test_live_inbox_bounds_pending_sequence_and_stop_publication(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        ready(store)
        svc = TrackingService(store, cfg)
        session = svc.pin(frame(), "synthetic", "owner", "pin")
        sid = session["id"]
        inbox = FrameInbox(store, cfg.tracking)
        with store.db:
            store.db.execute(
                "UPDATE tracking_streams SET phase='live' WHERE session_id=?", (sid,)
            )
        for i in range(1, 101):
            assert inbox.publish(sid, 1, record(i, i * 0.005), 0, 0)
        state = inbox.snapshot(sid)
        assert state["pending"] == 1 and state["pending_replacements"] == 99
        assert state["peak_live_pending"] == 1 and state["next_sequence"] == 101
        claimed = inbox.claim(sid, 1, 0, 0, now=0.51)
        assert claimed.sequence == 100 and claimed.record["frame_id"] == "fixture-100"
        assert inbox.snapshot(sid)["pending"] == 0
        for i in range(101, 111):
            inbox.publish(sid, 1, record(i, i * 0.005), 0, 0)
        assert claimed.record["frame_id"] == "fixture-100"
        assert inbox.snapshot(sid)["pending"] == 1
        with store.db:
            inbox.completed(sid, claimed.sequence, True, True)
        next_frame = inbox.claim(sid, 1, 100, 0.5, now=0.56)
        assert next_frame.sequence == 110 and next_frame.skipped == 9
        svc.stop(sid, "synthetic", "owner")
        assert inbox.publish(sid, 1, record(111, 0.555), 0, 0) is False
        assert inbox.claim(sid, 1, 110, 0.55, now=0.56) is None
        assert inbox.snapshot(sid)["phase"] == "closed"


def test_bootstrap_keeps_bounded_history_and_transitions_to_one_pending(cfg):
    cfg = replace(cfg, tracking=replace(cfg.tracking, frame_limit=4))
    with EvidenceStore(cfg.assistant.data_dir) as store:
        ready(store)
        svc = TrackingService(store, cfg)
        sid = svc.pin(frame(), "synthetic", "owner", "pin")["id"]
        inbox = FrameInbox(store, cfg.tracking)
        for i in range(1, 7):
            inbox.publish(sid, 1, record(i, i * 0.1), 0, 0)
        assert (
            store.db.execute(
                "SELECT COUNT(*) FROM tracking_frames WHERE session_id=?", (sid,)
            ).fetchone()[0]
            == 5
        )
        selected = inbox.claim(sid, 1, 0, 0, now=0.7)
        with store.db:
            inbox.completed(sid, selected.sequence, selected.was_head, True)
        if not selected.was_head:
            selected = inbox.claim(
                sid,
                1,
                selected.sequence,
                selected.record["capture_unix_ms"] / 1000,
                now=0.7,
            )
            with store.db:
                inbox.completed(sid, selected.sequence, selected.was_head, True)
        assert inbox.snapshot(sid)["phase"] == "live"
        for i in range(7, 100):
            inbox.publish(sid, 1, record(i, i * 0.1), 0, 0)
        assert inbox.snapshot(sid)["pending"] == 1
        assert (
            store.db.execute(
                "SELECT COUNT(*) FROM tracking_frames WHERE session_id=?", (sid,)
            ).fetchone()[0]
            == 2
        )


def test_legacy_session_is_not_silently_reinterpreted(cfg):
    with EvidenceStore(cfg.assistant.data_dir) as store:
        ready(store)
        svc = TrackingService(store, cfg)
        sid = svc.pin(frame(), "synthetic", "owner", "pin")["id"]
        with store.db:
            store.db.execute("DELETE FROM tracking_streams WHERE session_id=?", (sid,))
            profile = json.loads(
                store.db.execute(
                    "SELECT profile_json FROM tracking_sessions WHERE id=?", (sid,)
                ).fetchone()[0]
            )
            profile["profile_version"] = 1
            store.db.execute(
                "UPDATE tracking_sessions SET profile_json=? WHERE id=?",
                (json.dumps(profile), sid),
            )
        assert svc.get(sid, "synthetic")["stream"] is None
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_temporal_policy_has_no_framework_or_storage_import_dependency():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import teach_and_find.tracking_schedule; "
            "assert not ({'torch', 'cv2', 'sqlite3', 'fastapi'} & sys.modules.keys())",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_clock_regression_is_not_an_acceptable_latest_frame():
    with pytest.raises(AssistantError) as exc:
        select_frame(
            [(12, record(12, 9.9))],
            phase="live",
            previous_sequence=11,
            previous_capture=10,
            now=10.1,
            max_gap=0.6,
            max_age=1,
        )
    assert exc.value.code == "TRACKING_FRAME_GAP"
