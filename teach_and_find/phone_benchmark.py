"""Evaluator-only latency correlation; never used by perception or control."""

from datetime import datetime
import numpy as np


def summarize(values):
    if not values:
        return {"count": 0, "p50_ms": None, "p95_ms": None}
    return {
        "count": len(values),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "min_ms": float(min(values)),
        "max_ms": float(max(values)),
    }


def analyze_phone_trace(browser, trace):
    start, end = browser["measure_start_ms"], browser["measure_end_ms"]
    reference = browser["clock_reference"]
    epoch_offset = reference["host_unix_ms"] - reference["host_monotonic_ns"] / 1e6
    frames = {
        r["frame_id"]: {
            **r,
            "capture_ms": datetime.fromisoformat(r["captured_at"]).timestamp() * 1000,
        }
        for r in trace["frames"]
    }
    painted = {}
    for frame in browser["frames"]:
        time = frame["painted_client_unix_ms"]
        if start <= time <= end:
            painted.setdefault(frame["frame_id"], time)
    paints = sorted(painted.values())
    capture_age = [
        painted[key] - frames[key]["capture_ms"] for key in painted if key in frames
    ]
    events = [
        {**r, "unix_ms": epoch_offset + r["at"] * 1000} for r in trace["trajectory"]
    ]
    applied, feedback, trials = [], [], []
    for i, intent in enumerate(browser["inputs"]):
        upper = (
            browser["inputs"][i + 1]["at_ms"] if i + 1 < len(browser["inputs"]) else end
        )
        sign = 1 if intent["label"] == "Turn left" else -1
        command = next(
            (
                r
                for r in events
                if intent["at_ms"] <= r["unix_ms"] < upper
                and r["command"][1] * sign > 0
            ),
            None,
        )
        result = {
            "input_ms": intent["at_ms"],
            "label": intent["label"],
            "command_observed": command is not None,
            "visible_feedback": False,
        }
        if command:
            applied.append(command["unix_ms"] - intent["at_ms"])
            baseline = next(
                (
                    r["pose"]
                    for r in reversed(events)
                    if r["unix_ms"] < command["unix_ms"]
                ),
                None,
            )
            visible = [
                painted[key]
                for key, f in frames.items()
                if key in painted
                and command["unix_ms"] <= f["capture_ms"] < upper
                and baseline is not None
                and abs(f["pose"][2] - baseline[2]) > 1e-5
                and painted[key] < upper
            ]
            if visible:
                feedback.append(min(visible) - intent["at_ms"])
                result["visible_feedback"] = True
        trials.append(result)
    host_capture = [
        f["capture_ms"] for f in frames.values() if start <= f["capture_ms"] <= end
    ]
    return {
        "scope": "actual public tunnel, host-local touch Chromium and host clock; evaluator-only kinematic pose; no ROS/real phone/physical motion",
        "duration_s": (end - start) / 1000,
        "painted_frames": len(painted),
        "delivered_fps": len(painted) / ((end - start) / 1000),
        "host_captured_frames": len(host_capture),
        "host_capture_fps": len(host_capture) / ((end - start) / 1000),
        "paint_interval": summarize(np.diff(paints).tolist()),
        "capture_to_paint": summarize(capture_age),
        "input_to_applied_simulator_command": summarize(applied),
        "input_to_changed_pose_paint": summarize(feedback),
        "https_rtt": summarize(browser["rtt_ms"]),
        "trials": trials,
        "missing_commands": sum(not r["command_observed"] for r in trials),
        "missing_visual_feedback": sum(not r["visible_feedback"] for r in trials),
        "clock": "same OS clock for Chromium and Python; no physical-phone clock claim",
        "ai_enabled": False,
        "ros_in_path": False,
    }
