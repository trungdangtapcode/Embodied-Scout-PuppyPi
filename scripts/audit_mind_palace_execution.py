"""Explicit offline control-flow probe through actual pinned upstream source.

Injected responses are NOT model inference or algorithm-quality evidence. The
probe demonstrates which source functions the adapter executes. No API or robot
is contacted; the product has no such fixture-provider option.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from teach_and_find.config import Settings
from teach_and_find.mind_palace_adapter import MindPalaceAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-contract-probe", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = root / "docs/research/2026-11-01-mind-palace-app"
    captures = json.loads((evidence / "capture-state.json").read_text())["captures"]
    paths = {
        c["id"]: str(
            evidence / "inputs" / f"scene-{c['provenance']['fixture_index']}.png"
        )
        for c in captures
    }
    cfg = Settings()
    cfg = replace(
        cfg,
        memory=replace(
            cfg.memory,
            enabled=True,
            model="offline_contract_fixture",
            upstream_path=str(root / ".upstream/mind-palace"),
        ),
    )
    # Upstream constructors require the variable. This placeholder is never sent
    # anywhere: only the explicit injected client below supplies responses.
    os.environ.setdefault("OPENAI_API_KEY", "offline-control-flow-placeholder")
    events = []

    def create(**kwargs):
        stage = kwargs["response_format"]["json_schema"]["name"].removeprefix("memory_")
        fields = kwargs["response_format"]["json_schema"]["schema"]["properties"]
        if stage == "target":
            value = {
                "reasoning": "OFFLINE CONTROL-FLOW FIXTURE",
                "object": "fixture target",
            }
        elif stage == "episodes":
            value = {
                "reasoning_on_search_strategy": "OFFLINE FIXTURE",
                "search_strategy": "PAST_ONLY",
                "time": [fields["time"]["items"]["enum"][0]],
                "reasoning": "OFFLINE FIXTURE",
            }
        elif stage == "rooms":
            value = {
                "reasoning": "OFFLINE FIXTURE",
                "rooms": ["fixture region"],
                "room_id": [fields["room_id"]["items"]["enum"][0]],
                "probability": [0.5],
            }
        elif stage == "places":
            value = {
                "reasoning": "OFFLINE FIXTURE",
                "place_number": [fields["place_number"]["items"]["enum"][0]],
            }
        elif stage == "verify":
            value = {
                "answer": "True",
                "reasoning": "Injected fixture; not visual recognition.",
            }
        elif stage == "ready":
            value = {
                "ready_to_answer": "yes",
                "answer_or_explanation": "Injected fixture; not evidence sufficiency.",
            }
        elif stage == "answer":
            value = {
                "answer": "OFFLINE CONTROL-FLOW FIXTURE, NOT A MODEL ANSWER",
                "reasoning": "Injected fixture only",
                "citations": [fields["citations"]["items"]["enum"][0]],
                "claim_type": "recorded_visual",
            }
        else:
            raise AssertionError(stage)
        return SimpleNamespace(
            model="offline_contract_fixture",
            id="offline-contract-fixture",
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(refusal=None, content=json.dumps(value)),
                )
            ],
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    adapter = MindPalaceAdapter(
        cfg,
        lambda stage, record: events.append({"stage": stage, **record}),
        lambda: None,
        client=client,
    )
    upstream = (root / ".upstream/mind-palace/src").resolve()
    calls = {}

    def profile(frame, event, arg):
        if event != "call":
            return
        file = Path(frame.f_code.co_filename).resolve()
        if file.is_relative_to(upstream):
            key = str(file.relative_to(upstream)) + ":" + frame.f_code.co_qualname
            calls[key] = calls.get(key, 0) + 1

    sys.setprofile(profile)
    try:
        result = adapter.question("OFFLINE CONTROL-FLOW FIXTURE", captures, paths)
    finally:
        sys.setprofile(None)
    required = [
        "object_identification",
        "episodic_reasoning_v2",
        "value_based_room_selection",
        "direct_query_place_retrieval",
        "WorldModel.explore",
        "vlm_image_analysis",
        "BeliefManager.update_history",
        "check_ready_to_answer",
        "answer_the_question",
    ]
    for method in required:
        if not any(method in key for key in calls):
            raise AssertionError(f"Unexecuted upstream method: {method}")
    if any("move_robot" in key for key in calls):
        raise AssertionError("Benchmark movement simulation was invoked")
    output = {
        "schema_version": 1,
        "evidence_type": "offline_injected_control_flow_only",
        "model_inference_executed": False,
        "paid_api_calls": 0,
        "hardware_actuated": False,
        "fixture_return_is_not_capability_success": True,
        "upstream_revision": cfg.memory.upstream_revision,
        "required_upstream_entries_executed": required,
        "upstream_calls": calls,
        "upstream_file_sha256": {
            str(f.relative_to(upstream)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in {upstream / key.split(":")[0] for key in calls}
        },
        "adapter_source_sha256": hashlib.sha256(
            (root / "teach_and_find/mind_palace_adapter.py").read_bytes()
        ).hexdigest(),
        "fixture_stages": [e["stage"] for e in events if e.get("event") == "completed"],
        "result_label": result["answer"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {
                "evidence_type": output["evidence_type"],
                "required_entries": len(required),
                "paid_api_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
