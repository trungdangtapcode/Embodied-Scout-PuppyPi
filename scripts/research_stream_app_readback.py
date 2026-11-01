"""Screenshot persisted model evidence from a disposable copy; no model/API calls."""

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 18770)) == 0:
            parser.error("Port occupied; no reuse.")
    with tempfile.TemporaryDirectory(prefix="puppypi-evidence-readback-") as directory:
        shutil.copytree(args.source_run / "state", Path(directory) / "state")
        env = dict(
            os.environ,
            PUPPYPI_STREAM_RUN=directory,
            PUPPYPI_MEMORY_ENABLED="1",
            PUPPYPI_TRACKING_ENABLED="1",
            PYTHONPATH=str(root),
            PUPPYPI_SCREENSHOT_DIR=str(args.output.resolve()),
        )
        env.pop("OPENAI_API_KEY", None)
        with (Path(directory) / "server.log").open("w") as log:
            server = subprocess.Popen(
                [".venv-dev/bin/python", "scripts/research_stream_server.py"],
                cwd=root,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("Readback app exited.")
                    try:
                        urllib.request.urlopen(
                            "http://127.0.0.1:18770/api/health", timeout=1
                        ).close()
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise TimeoutError("Readback unavailable.")
                subprocess.run(
                    [
                        "node",
                        "--input-type=module",
                        "-e",
                        r"""
import { chromium } from './web/node_modules/@playwright/test/index.mjs';
const browser=await chromium.launch();
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto('http://127.0.0.1:18770');
 await page.getByLabel('Pairing code').fill('synthetic-stream-acceptance');
 await page.getByRole('button',{name:'Open Field Console'}).click();
 await page.getByRole('button',{name:'Room memory',exact:true}).click();
 await page.locator('.memory-answer-text').waitFor();
 const cited=page.getByAltText('Inspected capture at Rendered desk',{exact:true});
 await cited.scrollIntoViewIfNeeded();await cited.evaluate(img=>img.decode());
 await page.getByRole('region',{name:'Mind Palace result',exact:true}).screenshot({path:process.env.PUPPYPI_SCREENSHOT_DIR+'/readback-desktop-answer.png'});
 await page.setViewportSize({width:390,height:844});await cited.scrollIntoViewIfNeeded();await cited.evaluate(img=>img.decode());
 await page.getByRole('region',{name:'Mind Palace result',exact:true}).screenshot({path:process.env.PUPPYPI_SCREENSHOT_DIR+'/readback-phone-answer.png'});
} finally {await browser.close();}
""",
                    ],
                    cwd=root,
                    env=env,
                    check=True,
                    timeout=90,
                )
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    main()
