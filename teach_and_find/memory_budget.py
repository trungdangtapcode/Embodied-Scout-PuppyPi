"""Optional durable cap on paid attempts across jobs and worker restarts."""

import fcntl
import json
import os
from pathlib import Path
import time

from teach_and_find.storage import AssistantError


def reserve_call(cfg):
    if not cfg.global_call_budget_file:
        return
    if cfg.global_call_budget <= 0:
        raise AssistantError(
            "MODEL_GLOBAL_BUDGET_INVALID",
            "A positive explicit paid-call limit is required.",
        )
    path = Path(cfg.global_call_budget_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        text = stream.read()
        ledger = (
            json.loads(text)
            if text
            else {"limit": cfg.global_call_budget, "attempts": 0, "reserved_at": []}
        )
        if ledger["limit"] != cfg.global_call_budget:
            raise AssistantError(
                "MODEL_GLOBAL_BUDGET_CONFLICT",
                "The existing paid-call limit cannot be changed implicitly.",
            )
        if ledger["attempts"] >= ledger["limit"]:
            raise AssistantError(
                "MODEL_GLOBAL_BUDGET_EXHAUSTED",
                "The total authorized paid-call budget is exhausted.",
            )
        ledger["attempts"] += 1
        ledger["reserved_at"].append(time.time())
        stream.seek(0)
        stream.truncate()
        json.dump(ledger, stream)
        stream.flush()
        os.fsync(stream.fileno())
