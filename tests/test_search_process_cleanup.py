"""Disposable subprocess cancellation; no app, models, downloads or robot."""

import importlib.util
from pathlib import Path
import sys
import threading
import time


def test_cancelled_evaluation_waits_for_its_owned_process_cleanup(tmp_path):
    source = Path(__file__).resolve().parents[1] / "scripts/run_search_protocol.py"
    spec = importlib.util.spec_from_file_location("search_protocol_runner", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stopped = tmp_path / "stopped"
    ready = tmp_path / "ready"
    script = """import signal,time,sys
from pathlib import Path
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
Path('ready').write_text('ready')
try:
    while True: time.sleep(.05)
finally: Path('stopped').write_text('cleaned up')
"""
    cancelled = threading.Event()

    def cancel():
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        cancelled.set()

    thread = threading.Thread(target=cancel)
    thread.start()
    try:
        with (tmp_path / "log").open("w") as log:
            result = module.execute_owned(
                [sys.executable, "-c", script], tmp_path, log, cancelled, budget_s=4
            )
        assert result["intervention"] == "batch_cancelled"
        assert stopped.read_text() == "cleaned up"
    finally:
        cancelled.set()
        thread.join(4)
