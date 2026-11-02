"""Execute released planning/control examples without modifying upstream source."""

import importlib.util
import json
from pathlib import Path
import sys

from teach_and_find.config import Settings
from teach_and_find.search_navigation import ROBOTICS_REVISION, pinned_source


def main():
    root = pinned_source(Settings().search.robotics_source, ROBOTICS_REVISION)
    sys.path.insert(0, str(root))
    modules = []
    for name, relative in [
        ("astar_example", "PathPlanning/AStar/a_star.py"),
        ("pose_example", "PathTracking/move_to_pose/move_to_pose.py"),
    ]:
        spec = importlib.util.spec_from_file_location(name, root / relative)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.show_animation = False
        modules.append(module)
    calls = {}

    def trace(frame, event, arg):
        if (
            event == "call"
            and frame.f_code.co_name in {"planning", "calc_control_command"}
            and str(root) in frame.f_code.co_filename
        ):
            key = frame.f_code.co_qualname
            calls[key] = calls.get(key, 0) + 1

    sys.setprofile(trace)
    try:
        modules[0].main()
        x, y, v, w = modules[1].move_to_pose(0.0, 0.0, 0.0, 1.0, 1.0, 1.57)
    finally:
        sys.setprofile(None)
    destination = Path(
        "runs/completion-research-2026-11-02/navigation-upstream-example.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "revision": ROBOTICS_REVISION,
                "original_astar_main_executed": True,
                "original_move_to_pose_example_function": True,
                "executed_calls": calls,
                "controller_last_logged_xy": [x[-1], y[-1]],
                "logged_steps": len(x),
                "v": v,
                "w": w,
            },
            indent=2,
        )
    )
    print(calls, [x[-1], y[-1]])


if __name__ == "__main__":
    main()
