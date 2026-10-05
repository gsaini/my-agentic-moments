"""Structured calls to Claude, plus a scripted stand-in for offline tests.

Every node that asks the model something gets back a validated Pydantic object,
not free text: the schema is the contract between nodes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"
# Server-side refusal fallbacks (`fallbacks: "default"`) on the Claude API.
_FALLBACKS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_EFFORT = _FALLBACKS | {"claude-sonnet-5"}


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.calls + other.calls, self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


class LLMError(Exception):
    """The model declined (refusal) or returned something that doesn't fit the schema."""


class LLM(Protocol):
    name: str

    def ask(self, *, role: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        """Ask for an object of type `schema`. `role` names the node asking (for tracing and scripting)."""


class ClaudeLLM:
    def __init__(
        self,
        name: str = DEFAULT_MODEL,
        *,
        effort: str = "medium",
        max_tokens: int = 16_000,
        client: anthropic.Anthropic | None = None,
    ):
        self.name = name
        self.effort = effort
        self.max_tokens = max_tokens  # thinking counts toward this, so don't size it for the answer alone
        self.client = client or anthropic.Anthropic(max_retries=4)

    def ask(self, *, role: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        kwargs: dict = {
            "model": self.name,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "output_format": schema,  # the SDK turns the Pydantic model into a JSON schema and validates the reply
        }
        if self.name in _EFFORT:
            kwargs["output_config"] = {"effort": self.effort}  # Opus 5.5 defaults to medium; be explicit
        if self.name in _FALLBACKS:
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        # Read the stop reason before the SDK parses the reply: a refusal or a cut-off
        # answer is not valid JSON, and should be reported as what it is.
        raw = self.client.beta.messages.with_raw_response.parse(**kwargs)
        body = raw.http_response.json()
        if body.get("stop_reason") == "refusal":
            raise LLMError(f"{role}: the model declined ({body.get('stop_details')})")
        if body.get("stop_reason") == "max_tokens":
            raise LLMError(f"{role}: the reply was cut off at max_tokens ({self.max_tokens})")
        try:
            response = raw.parse()
        except ValidationError as exc:
            raise LLMError(f"{role}: the reply did not match {schema.__name__}: {exc.errors()[0]['msg']}") from exc
        if response.parsed_output is None:
            raise LLMError(f"{role}: no {schema.__name__} in the reply (stop_reason={response.stop_reason})")
        usage = Usage(1, response.usage.input_tokens or 0, response.usage.output_tokens or 0)
        return response.parsed_output, usage


class ScriptedLLM:
    """Replays prepared answers, per role, in order. For tests and offline demos — not for measuring anything."""

    name = "scripted"

    def __init__(self, script: dict[str, list[BaseModel | Callable[[str], BaseModel]]]):
        self.script = {role: list(answers) for role, answers in script.items()}
        self.prompts: list[tuple[str, str]] = []  # (role, prompt) — so tests can check what each node saw

    def ask(self, *, role: str, system: str, prompt: str, schema: type[T]) -> tuple[T, Usage]:
        self.prompts.append((role, prompt))
        answers = self.script.get(role) or []
        if not answers:
            raise LLMError(f"scripted LLM has no answer left for role {role!r}")
        answer = answers.pop(0)
        if callable(answer) and not isinstance(answer, BaseModel):
            answer = answer(prompt)
        if not isinstance(answer, schema):
            raise LLMError(f"scripted answer for {role!r} is a {type(answer).__name__}, expected {schema.__name__}")
        return answer, Usage(1, len(system + prompt) // 4, 100)
