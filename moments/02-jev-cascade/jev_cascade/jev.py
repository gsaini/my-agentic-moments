"""Jev through the official TypeSafe SDK: live, or scripted over a mock transport for offline runs.

The model is pinned to a versioned ID. Aliases move when TypeSafe ships a release (on 2026-10-21
`jev-latest` is 1.13.0 and `jev-preview` is 1.14.0, https://docs.typesafe.ai/models), and an
experiment whose model changes halfway through measures nothing. Every answer records its model.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Mapping

import httpx2
from typesafe_sdk import RetryPolicy, TypeSafeClient
from typesafe_sdk.constants import API_KEY_ENV

from jev_cascade.dataset import Request
from jev_cascade.routes import CHECKS, QUESTIONS, state_for
from jev_cascade.schema import AskJev, Judgment

JEV_MODEL = "jev-1.13.0"
# List price, https://docs.typesafe.ai/models (checked 2026-10-21): $42 per billion input tokens,
# output tokens free. Re-check before quoting a cost.
PRICE_PER_INPUT_TOKEN = 42 / 1_000_000_000

# A scripted answer per question name: a Choice's probabilities by label, or a Noul's P(yes).
Script = Mapping[str, Mapping[str, float] | float]


def has_key() -> bool:
    return bool(os.environ.get(API_KEY_ENV, "").strip())


def live_client() -> TypeSafeClient:
    """Jev itself. Reads TYPESAFE_API_KEY."""
    return TypeSafeClient()


def asker(client: TypeSafeClient, model: str = JEV_MODEL) -> AskJev:
    """One request per call: all six questions, answered in parallel against the request."""

    def ask(request: Request) -> Judgment:
        started = time.perf_counter()
        response = client.system_one(state=state_for(request.text), questions=QUESTIONS, model=model)
        latency_ms = (time.perf_counter() - started) * 1000
        route, reordered = response.choices["route"], response.choices["route_reordered"]
        return Judgment(
            route=route.choice,
            probabilities=dict(route.probabilities),
            confidence=route.confidence,
            reordered=reordered.choice,
            checks={name: response.nouls[f"needs_{name}"].noul for name in CHECKS},
            model=response.model,
            input_tokens=response.usage.input_tokens or 0,
            latency_ms=latency_ms,
        )

    return ask


def scripted_client(scripts: Mapping[str, Script], seen: list[dict] | None = None) -> TypeSafeClient:
    """The real SDK, answered from scripts keyed by request text. For tests and the demo — this is not Jev.

    A question without a script gets a maximally uncertain answer: a uniform Choice, a Noul of 0.5.
    """

    def handle(http: httpx2.Request) -> httpx2.Response:
        body = json.loads(http.content)
        if seen is not None:
            seen.append(body)
        script = scripts.get(body["state"]["request"], {})
        answers = {}
        for name, question in body["questions"].items():
            given = script.get(name)
            if question["type"] == "choice":
                labels = list(question["criteria"])
                probs = {label: given.get(label, 0.0) for label in labels} if isinstance(given, Mapping) else {}
                probs = probs or {label: 1 / len(labels) for label in labels}
                best = max(labels, key=probs.__getitem__)
                answers[name] = {"type": "choice", "choice": best, "confidence": choice_confidence(probs.values()),
                                 "probabilities": probs}  # fmt: skip
            else:
                answers[name] = {"type": "noul", "noul": 0.5 if given is None else float(given)}
        usage = {"input_tokens": len(http.content) // 4, "output_tokens": 0}
        return httpx2.Response(200, json={"model": "scripted", "answers": answers, "usage": usage})

    return TypeSafeClient(
        api_key="scripted",
        transport=httpx2.MockTransport(handle),
        retry=RetryPolicy(max_retries=0),
        compression=False,  # keep bodies readable for the handler (zstd is on by default where available)
    )


def choice_confidence(probabilities: Iterable[float]) -> float:
    """TypeSafe's documented formula, (n * peak - 1) / (n - 1): 0 for a uniform spread, 1 for a sure pick."""
    p = list(probabilities)
    if len(p) < 2:
        return 1.0
    return max(0.0, min(1.0, (len(p) * max(p) - 1) / (len(p) - 1)))


def cost_usd(input_tokens: int) -> float:
    return input_tokens * PRICE_PER_INPUT_TOKEN
