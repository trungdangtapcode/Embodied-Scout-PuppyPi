"""Bounded isolated mandatory inference; no queue, fallback or motion ownership."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import select
import subprocess
import time
from uuid import uuid4

from teach_and_find.errors import AssistantError


class AppearanceVerifier:
    def __init__(self, store, cfg, vision, references, check):
        self.check, self.timeout = check, cfg.anomaly_timeout_s
        self.process = None
        self.log = (store.root / "anomaly-worker.log").open("a")
        try:
            if not Path(cfg.anomaly_python).is_file():
                raise AssistantError(
                    "ANOMALY_ENVIRONMENT_MISSING",
                    "Required isolated CPU interpreter is missing; run make search-setup.",
                )
            self.process = subprocess.Popen(
                [cfg.anomaly_python, "-m", "teach_and_find.anomaly_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.log,
                text=True,
                bufsize=1,
                env={**os.environ, "CUDA_VISIBLE_DEVICES": "-1"},
            )
            self.send(
                {
                    "search": asdict(cfg),
                    "vision": asdict(vision),
                    "store": str(store.root),
                    "references": references,
                }
            )
            response = self.receive()
            if response.get("type") != "ready":
                raise AssistantError(
                    "ANOMALY_PROTOCOL_INVALID",
                    "Required model initialization did not complete.",
                )
            self.provenance = response["provenance"]
        except BaseException:
            self.close()
            raise

    def send(self, message):
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise AssistantError(
                "ANOMALY_PROCESS_LOST", "Required inference process stopped."
            ) from error

    def receive(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            self.check()
            if select.select([self.process.stdout], [], [], 0.1)[0]:
                line = self.process.stdout.readline()
                if not line:
                    raise AssistantError(
                        "ANOMALY_PROCESS_LOST",
                        "Required inference process disconnected.",
                    )
                response = json.loads(line)
                if response.get("type") == "error":
                    raise AssistantError(response["code"], response["message"])
                return response
        raise AssistantError(
            "ANOMALY_TIMEOUT",
            "Required original inference exceeded its bounded deadline; no substitute.",
        )

    def assess(self, candidates):
        request_id = str(uuid4())
        crops = [candidate["crop_image_sha"] for candidate in candidates]
        self.send({"request_id": request_id, "crops": crops})
        response = self.receive()
        records = response.get("records", [])
        if (
            response.get("request_id") != request_id
            or [r["crop_image_sha"] for r in records] != crops
        ):
            raise AssistantError(
                "ANOMALY_PROTOCOL_INVALID",
                "Response does not correspond to the requested real crops.",
            )
        self.provenance = {
            **self.provenance,
            "executed_scoring_calls": response["executed_scoring_calls"],
        }
        return records

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
        self.log.close()
