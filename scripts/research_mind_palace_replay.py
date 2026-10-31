"""Run genuine upstream Mind Palace components on one public-image replay.

Explicitly invokes paid API inference. Requires the separately installed, pinned
upstream repository and an image supplied by the caller. This is a component
experiment, not the LA-EQA benchmark, app integration or a navigation test.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from types import MethodType


def load_bashrc_credentials() -> None:
    """Read the user-designated environment without printing or saving secrets."""
    prefix = "PUPPYPI_AUDIT_CONFIG="
    code = (
        "import json,os; print(\"PUPPYPI_AUDIT_CONFIG=\"+json.dumps({"
        "k:os.environ.get(k) for k in (\"OPENAI_API_KEY\",\"OPENAI_BASE_URL\","
        "\"OPENAI_ORGANIZATION\",\"OPENAI_PROJECT\")}))"
    )
    # Pass the Python program as a positional argument, not interpolated shell code.
    process = subprocess.run(
        ["bash", "-ic", 'python3 -c "$1"', "puppypi-research", code],
        capture_output=True, text=True, timeout=30, check=True,
    )
    lines = [line for line in process.stdout.splitlines() if line.startswith(prefix)]
    if not lines:
        raise RuntimeError("No structured credential configuration from bashrc")
    for key, value in json.loads(lines[-1][len(prefix):]).items():
        if value:
            os.environ[key] = value


def configure_interface(interface, args: argparse.Namespace, calls: list[dict]) -> None:
    """Select the requested model; adapt transport without changing graph logic."""
    interface.openai_model = args.model
    interface.openai_vision_model = args.model
    if args.api_mode == "upstream":
        return

    def call_chat(self, messages, vision_query=False, verbose=False):
        from openai import OpenAI

        payload = {
            "model": args.model,
            "messages": messages,
            "max_completion_tokens": self.openai_max_tokens,
            "reasoning_effort": args.reasoning_effort,
            "response_format": {"type": "json_object"},
        }
        if args.reasoning_effort == "none":
            payload["temperature"] = self.openai_temperature
        # No retries or alternate backend: a request failure terminates the run.
        client = OpenAI(timeout=args.request_timeout_s, max_retries=0)
        response = client.chat.completions.create(**payload)
        calls.append({
            "requested_model": args.model,
            "returned_model": response.model,
            "vision_query": vision_query,
            "has_image_input": any(
                isinstance(message.get("content"), list)
                and any(item.get("type") == "image_url" for item in message["content"])
                for message in messages
            ),
            "usage": response.usage.model_dump() if response.usage else None,
        })
        if response.model != args.model and not response.model.startswith(args.model + "-"):
            raise ValueError("API returned a different model; no fallback accepted")
        if len(response.choices) != 1:
            raise ValueError("Expected exactly one model response")
        choice = response.choices[0]
        if choice.finish_reason != "stop" or choice.message.refusal:
            raise ValueError("Model response was incomplete or refused; no fallback")
        if not isinstance(choice.message.content, str) or not choice.message.content.strip():
            raise ValueError("Model returned empty content; no fallback")
        return choice.message.content

    interface.call_openai_api = MethodType(call_chat, interface)


def execute(args: argparse.Namespace) -> dict:
    from contextual_long_term_reasoning import mind_palace_generation
    from contextual_long_term_reasoning.openai_interface import OpenAIInterface
    from contextual_long_term_reasoning.mind_palace_generation import PlaceNode, RoomNode, SceneGraph
    from contextual_long_term_reasoning.belief_manager import BeliefManager, WorldModel
    from contextual_long_term_reasoning.eqa_reasoning import EQAReasoning
    from contextual_long_term_reasoning.mind_palace_exploration import MindPalaceExploration

    repository = args.upstream.resolve()
    revision = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != args.revision:
        raise ValueError("Upstream revision differs from the requested revision")
    subprocess.run(["git", "-C", str(repository), "diff", "--quiet", "HEAD"], check=True)
    if not Path(mind_palace_generation.__file__).resolve().is_relative_to(repository / "src"):
        raise ValueError("Imported implementation is not from the requested checkout")
    image = args.image.resolve()
    result = {
        "status": "FAIL",
        "repository": "https://github.com/mind-palace-laeqa/benchmark",
        "revision": revision,
        "profile": "custom one-image replay using upstream memory/reasoning and an explicit API profile",
        "model": args.model,
        "vision_model": args.model,
        "api_mode": args.api_mode,
        "reasoning_effort": args.reasoning_effort,
        "api_calls": [],
        "input_source": args.source_url,
        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "question": args.question,
        "fallback": False,
        "source_changes": False,
        "gpu_used": False,
        "limitations": [
            "not the reference benchmark",
            "not integrated into PuppyPi app",
            "nominal one-view region/pose metadata supplied by the harness",
            "capture time is unknown; episode ID denotes replay order only",
            "no navigation or metric geometry claim",
            "no exact-instance or continuous-coverage evaluation",
            "one image/question is not an accuracy benchmark",
        ],
        "steps": [],
    }
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "replay.log").open("w") as log:
        try:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                interface = OpenAIInterface()
                configure_interface(interface, args, result["api_calls"])
                result["model"] = interface.openai_model
                result["vision_model"] = interface.openai_vision_model
                prompt = (
                    "Describe only visible contents of this image. Return a valid JSON "
                    "object with keys objects (a list of visible object names) and "
                    "description (a brief description). Return JSON only, without "
                    "Markdown or code fences. Do not infer unseen content or a camera location."
                )
                messages = interface.prepare_openai_vision_messages(prompt, "", [str(image)])
                raw = interface.call_openai_api(messages, vision_query=True)
                result["caption_raw"] = raw
                caption = interface.answer_to_json(raw)
                if not isinstance(caption.get("objects"), list) or not isinstance(caption.get("description"), str):
                    raise ValueError("Invalid caption schema")
                result["caption"] = caption
                result["steps"].append("vision_caption_from_upstream_interface")

                # Input adapter: these nominal coordinates are never motion targets.
                # Every semantic description comes from the actual VLM response.
                place = PlaceNode(0, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0], 0.0)
                place.room_parent = "r1"
                place.image_path = str(image)
                place.text_object_seen = str(caption["objects"])
                place.text_contextual_description = caption["description"]
                room = RoomNode("r1", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0], 0.0)
                room.room_name = "Recorded viewpoint"
                room.text_object_seen = str(caption["objects"])
                room.text_contextual_description = caption["description"]
                graph = SceneGraph("one_view_replay", str(args.output), {"r1": room}, {0: place})
                memory = {"replay_step_0": graph}
                belief = BeliefManager(args.question, memory)
                world = WorldModel(memory)
                eqa = EQAReasoning()
                exploration = MindPalaceExploration()
                for upstream_interface in (
                    eqa.oa_interface,
                    exploration.oa_interface,
                    exploration.episodic_exploration.oa_interface,
                    exploration.room_exploration.oa_interface,
                    exploration.place_exploration.oa_interface,
                ):
                    configure_interface(upstream_interface, args, result["api_calls"])
                belief.y_object_to_search, belief.y_reasoning_to_search_object = eqa.object_identification(belief)
                result["target"] = belief.y_object_to_search
                result["steps"].append("upstream_object_identification")
                episodes, strategy, _, _ = exploration.episodic_exploration.episodic_reasoning_v2(belief)
                result["episode_selection"] = {"episodes": episodes, "strategy": strategy}
                result["steps"].append("upstream_episodic_reasoning")
                if len(episodes) != 1 or episodes[0] not in memory:
                    raise ValueError("Upstream did not select the available recorded episode")
                episode = episodes[0]
                room_id, _ = exploration.room_exploration.plan(belief, episode, 0)
                if room_id not in graph.room_nodes:
                    raise ValueError("Upstream selected an unavailable room")
                result["room_selection"] = room_id
                result["steps"].append("upstream_room_selection")
                # Its plan() method can fall back to unvisited places. Call direct
                # retrieval and fail on an empty/invalid answer instead.
                places = exploration.place_exploration.direct_query_place_retrieval(
                    belief.Q_user_question, belief.y_object_to_search, graph,
                    belief.x_robot_location, room_id, belief.H_a_place_exploration_action_history,
                )
                if not places or any(place_id not in graph.place_nodes for place_id in places):
                    raise ValueError("Upstream returned empty/invalid viewpoints; no fallback")
                result["place_selection"] = places
                result["steps"].append("upstream_place_retrieval_without_fallback")
                images, paths = world.explore(episode, places, show_images=False)
                if len(paths) != len(places):
                    raise ValueError("Missing selected source images; no fallback")
                result["steps"].append("upstream_memory_image_retrieval")
                found, insight = exploration.vlm_image_analysis(paths, belief)
                result["visual_verification"] = {"found": found, "insight": insight}
                if not found:
                    raise ValueError("Upstream VLM did not verify the requested visual target")
                belief.update_history(insight, images, paths, episode, room_id, places)
                result["steps"].append("upstream_visual_verification_and_history")
                ready, explanation = eqa.check_ready_to_answer(belief)
                result["ready"] = ready
                result["ready_explanation"] = explanation
                if not ready:
                    raise ValueError("Upstream reasoning not ready to answer; no fallback")
                answer, reasoning = eqa.answer_the_question(belief)
                result["answer"] = answer
                result["answer_reasoning"] = reasoning
                result["steps"].append("upstream_grounded_answer")
                result["status"] = "PASS_COMPONENT_REPLAY"
        except Exception as error:
            result["error_type"] = type(error).__name__
            message = str(error)
            secret = os.environ.get("OPENAI_API_KEY")
            result["error"] = message.replace(secret, "[REDACTED]") if secret else message
            # Avoid persisting third-party exceptions that could contain a credential.
            log.write(f"Experiment failed: {result['error_type']}\n")
    result["elapsed_s"] = round(time.monotonic() - started, 3)
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True, help="Exact requested model; no implicit default")
    parser.add_argument("--api-mode", choices=("upstream", "chat-completions"), required=True)
    parser.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--request-timeout-s", type=float)
    parser.add_argument("--from-bashrc", action="store_true")
    args = parser.parse_args()
    if args.api_mode == "chat-completions":
        if args.reasoning_effort is None or args.request_timeout_s is None or args.request_timeout_s <= 0:
            parser.error("Chat Completions requires explicit reasoning effort and a positive timeout")
    if args.from_bashrc:
        load_bashrc_credentials()
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required; no fallback")
    result = execute(args)
    print(json.dumps({key: result.get(key) for key in ("status", "model", "answer", "elapsed_s", "error_type")}, indent=2))
    return 0 if result["status"] == "PASS_COMPONENT_REPLAY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
