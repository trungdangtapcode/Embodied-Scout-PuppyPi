"""Measure a dedicated remote-only tunnel session and stop only that session."""

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from teach_and_find.config import Settings
from teach_and_find.phone_benchmark import analyze_phone_trace


def main():
    cfg = Settings().phone
    active = ROOT / cfg.run_dir / "active.json"
    if active.exists() and json.loads(active.read_text()).get("status") in {
        "ready",
        "starting",
    }:
        raise RuntimeError(
            "Stop the current phone session with make phone-stop before benchmarking."
        )
    python = str(ROOT / ".venv-dev/bin/python")
    subprocess.run(
        [python, "scripts/phone_session.py", "start", "--background", "--measure"],
        cwd=ROOT,
        check=True,
    )
    session = json.loads(active.read_text())
    run = Path(session["run"])
    try:
        subprocess.run(
            ["node", "web/scripts/benchmark-phone.mjs", str(active)],
            cwd=ROOT,
            check=True,
            timeout=150,
        )
    finally:
        subprocess.run(
            [python, "scripts/phone_session.py", "stop", "--run", str(run)],
            cwd=ROOT,
            check=True,
        )
    browser = json.loads((run / "browser-measurement.json").read_text())
    trace = json.loads((run / "trace.json").read_text())
    report = analyze_phone_trace(browser, trace)
    (run / "benchmark-summary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "trials"}, indent=2))
    if report["missing_commands"] or report["missing_visual_feedback"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
