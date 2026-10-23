import json

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from agentic.llm import ClaudeLLM, LLMError, ScriptedLLM, has_credentials


class Verdict(BaseModel):
    ok: bool
    reason: str


def fake_api(captured: dict, *, stop_reason="end_turn", text: str | None = '{"ok": true, "reason": "fine"}'):
    def handler(request):
        captured["body"] = json.loads(request.content)
        captured["beta"] = request.headers.get("anthropic-beta")
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [] if text is None else [{"type": "text", "text": text}],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 120, "output_tokens": 30},
        })  # fmt: skip

    return anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_request_shape_and_parsed_result():
    captured: dict = {}
    llm = ClaudeLLM(client=fake_api(captured))
    verdict, usage = llm.ask(role="critique", system="You review.", prompt="Review this.", schema=Verdict)
    body = captured["body"]
    assert body["model"] == "claude-opus-5-5" and body["max_tokens"] == 16_000
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"  # structured output from the Pydantic model
    assert body["fallbacks"] == "default" and captured["beta"] == "server-side-fallback-2026-07-01"
    assert not {"temperature", "top_p", "top_k", "thinking"} & set(body)
    assert verdict == Verdict(ok=True, reason="fine")
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (1, 120, 30)


def ask(client) -> None:
    ClaudeLLM(client=client).ask(role="critique", system="s", prompt="p", schema=Verdict)


def test_refusal_truncation_and_bad_output_become_llm_errors():
    with pytest.raises(LLMError, match="declined"):
        ask(fake_api({}, stop_reason="refusal", text=None))  # a refusal before any output has no content
    with pytest.raises(LLMError, match="cut off at max_tokens"):
        ask(fake_api({}, stop_reason="max_tokens", text='{"ok": tr'))
    with pytest.raises(LLMError, match="did not match Verdict"):
        ask(fake_api({}, text='{"ok": "maybe"}'))


def test_models_without_effort_or_fallbacks():
    captured: dict = {}
    ClaudeLLM("claude-haiku-4-5", client=fake_api(captured)).ask(role="x", system="s", prompt="p", schema=Verdict)
    assert "fallbacks" not in captured["body"] and captured["beta"] is None
    assert "effort" not in captured["body"].get("output_config", {})


def test_haiku_5_5_takes_effort_but_has_no_server_side_fallback():
    captured: dict = {}
    llm = ClaudeLLM("claude-haiku-5-5", effort="low", client=fake_api(captured))
    llm.ask(role="x", system="s", prompt="p", schema=Verdict)
    assert captured["body"]["output_config"]["effort"] == "low"  # its default is medium; be explicit
    assert "fallbacks" not in captured["body"] and captured["beta"] is None


def test_credentials_from_the_environment_or_a_profile(monkeypatch, tmp_path):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert not has_credentials()
    (tmp_path / "anthropic").mkdir()  # what `ant auth login` leaves behind
    assert has_credentials()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert has_credentials()


def test_scripted_llm_checks_its_script():
    llm = ScriptedLLM({"a": [Verdict(ok=True, reason="r")]})
    assert llm.ask(role="a", system="s", prompt="p", schema=Verdict)[0].ok
    with pytest.raises(LLMError, match="no answer left"):
        llm.ask(role="a", system="s", prompt="p", schema=Verdict)
