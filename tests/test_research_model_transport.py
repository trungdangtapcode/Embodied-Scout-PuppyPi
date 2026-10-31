"""Model routing and failure contracts; no SDK, network or paid API required."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    "research_replay", Path(__file__).resolve().parents[1] / "scripts/research_mind_palace_replay.py"
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def interface():
    def forbidden_upstream_call(*args, **kwargs):
        raise AssertionError("The requested model must not fall back to the old transport")

    return SimpleNamespace(
        openai_model="gpt-4o", openai_vision_model="gpt-4o",
        openai_max_tokens=512, openai_temperature=0.2,
        call_openai_api=forbidden_upstream_call,
    )


def response(**overrides):
    values = dict(model="gpt-6-luna", finish_reason="stop", refusal=None, content='{"ok": true}')
    values.update(overrides)
    return SimpleNamespace(
        model=values["model"], usage=None,
        choices=[SimpleNamespace(
            finish_reason=values["finish_reason"],
            message=SimpleNamespace(refusal=values["refusal"], content=values["content"]),
        )],
    )


def configure(monkeypatch, create, effort="none"):
    configurations = []

    def factory(**kwargs):
        configurations.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=factory))
    target = interface()
    calls = []
    args = SimpleNamespace(
        model="gpt-6-luna", api_mode="chat-completions",
        reasoning_effort=effort, request_timeout_s=60,
    )
    replay.configure_interface(target, args, calls)
    return target, calls, configurations


@pytest.mark.parametrize("effort", ["none", "medium"])
def test_requested_model_and_compatible_parameters(monkeypatch, effort):
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return response()

    target, calls, configurations = configure(monkeypatch, create, effort)
    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "fixture"}}]}]
    assert target.call_openai_api(messages, vision_query=True) == '{"ok": true}'
    request = requests[0]
    assert request["model"] == target.openai_model == target.openai_vision_model == "gpt-6-luna"
    assert request["reasoning_effort"] == effort
    assert request["max_completion_tokens"] == 512
    assert "max_tokens" not in request and "seed" not in request
    assert ("temperature" in request) == (effort == "none")
    assert configurations == [{"timeout": 60, "max_retries": 0}]
    assert calls[0]["returned_model"] == "gpt-6-luna"
    assert calls[0]["has_image_input"] is True


def test_request_failure_is_terminal(monkeypatch):
    attempts = []

    def fail(**kwargs):
        attempts.append(kwargs["model"])
        raise RuntimeError("Provider unavailable")

    target, calls, _ = configure(monkeypatch, fail)
    with pytest.raises(RuntimeError, match="Provider unavailable"):
        target.call_openai_api([])
    assert attempts == ["gpt-6-luna"]
    assert calls == []


@pytest.mark.parametrize("override", [
    {"model": "gpt-4o"},
    {"finish_reason": "length"},
    {"refusal": "Cannot answer"},
    {"content": ""},
])
def test_invalid_provider_response_cannot_pass(monkeypatch, override):
    target, calls, _ = configure(monkeypatch, lambda **kwargs: response(**override))
    with pytest.raises(ValueError):
        target.call_openai_api([])
    assert len(calls) == 1
