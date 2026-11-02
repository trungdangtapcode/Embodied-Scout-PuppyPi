"""Phone lifecycle ownership and evaluator invariants; no tunnel or model calls."""

import importlib.util
from pathlib import Path

from teach_and_find.phone_benchmark import analyze_phone_trace


def test_missing_or_reused_pid_never_counts_as_owned(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/phone_session.py"
    spec = importlib.util.spec_from_file_location("phone_session_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "process_stamp", lambda pid: None)
    assert not module.owned_alive({"pid": 123, "start_ticks": None})
    assert not module.owned_alive({"pid": 123, "start_ticks": "old"})
    monkeypatch.setattr(module, "process_stamp", lambda pid: "new")
    assert not module.owned_alive({"pid": 123, "start_ticks": "old"})
    assert module.owned_alive({"pid": 123, "start_ticks": "new"})


def fixture():
    browser = {
        "measure_start_ms": 1000,
        "measure_end_ms": 2000,
        "clock_reference": {"host_unix_ms": 1000, "host_monotonic_ns": 0},
        "inputs": [
            {"at_ms": 1100, "label": "Turn left"},
            {"at_ms": 1500, "label": "Turn right"},
        ],
        "frames": [
            {"frame_id": "a", "painted_client_unix_ms": 1300},
            {"frame_id": "a", "painted_client_unix_ms": 1320},
            {"frame_id": "b", "painted_client_unix_ms": 1700},
        ],
        "rtt_ms": [80, 100],
    }
    trace = {
        "trajectory": [
            {"at": 0, "pose": [0, 0, 0], "command": [0, 0]},
            {"at": 0.13, "pose": [0, 0, 0.2], "command": [0, 1]},
            {"at": 0.4, "pose": [0, 0, 0.2], "command": [0, 0]},
            {"at": 0.53, "pose": [0, 0, 0], "command": [0, -1]},
        ],
        "frames": [
            {
                "frame_id": "a",
                "captured_at": "1970-01-01T00:00:01.200000+00:00",
                "pose": [0, 0, 0.2],
            },
            {
                "frame_id": "b",
                "captured_at": "1970-01-01T00:00:01.600000+00:00",
                "pose": [0, 0, 0],
            },
        ],
    }
    return browser, trace


def test_latency_correlates_direction_and_unique_painted_frame():
    browser, trace = fixture()
    r = analyze_phone_trace(browser, trace)
    assert r["delivered_fps"] == 2
    assert r["capture_to_paint"]["p50_ms"] == 100
    assert r["input_to_applied_simulator_command"]["p50_ms"] == 30
    assert r["input_to_changed_pose_paint"]["p50_ms"] == 200
    assert r["missing_commands"] == r["missing_visual_feedback"] == 0


def test_lost_feedback_is_counted_not_reassigned_to_another_pulse():
    browser, trace = fixture()
    browser["frames"] = browser["frames"][:2]
    r = analyze_phone_trace(browser, trace)
    assert r["missing_visual_feedback"] == 1
    assert r["input_to_changed_pose_paint"]["count"] == 1
    assert r["input_to_applied_simulator_command"]["count"] == 2


def test_evaluator_trace_flushes_in_runtime_shutdown(tmp_path, monkeypatch):
    """Uvicorn SIGTERM can bypass code after run(); data belongs in close()."""
    import json
    from types import SimpleNamespace

    path = Path(__file__).resolve().parents[1] / "scripts/phone_app_server.py"
    spec = importlib.util.spec_from_file_location("phone_server_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime = module.PhoneRuntime.__new__(module.PhoneRuntime)
    runtime.trace = str(tmp_path / "trace.json")
    runtime.device = SimpleNamespace(evaluation_trajectory=[], evaluation_frames=[])

    def base_close(self):
        self.device.evaluation_frames.append({"frame_id": "shutdown-final-frame"})

    monkeypatch.setattr(module.OperatorRuntime, "close", base_close)
    runtime.close()
    assert json.loads(Path(runtime.trace).read_text())["frames"] == [
        {"frame_id": "shutdown-final-frame"}
    ]
