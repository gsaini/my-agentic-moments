"""What flows between the nodes: each model's answer (and how it is asked for), and the graph state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from agentic.llm import Usage
from jev_cascade.dataset import Request
from jev_cascade.routes import Route

# --- What the models return -------------------------------------------------------


class RouteAnswer(BaseModel):
    """Claude's answer."""

    route: Route
    reason: str = Field(description="One short sentence: what in the request decides the route.")


@dataclass(frozen=True)
class Judgment:
    """Jev's answers to one request, lifted out of the SDK response."""

    route: str  # the `route` Choice's pick
    probabilities: dict[str, float]
    confidence: float  # how concentrated `probabilities` is — not whether the pick is right
    reordered: str  # the pick of the same Choice with its options in reverse order
    checks: dict[str, float]  # P(yes) from each specialist's own Noul
    model: str
    input_tokens: int
    latency_ms: float


@dataclass(frozen=True)
class ClaudeCall:
    answer: RouteAnswer
    usage: Usage
    model: str
    latency_ms: float


# A node asks a model through one of these. They take the request and nothing else.
AskJev = Callable[[Request], Judgment]
AskClaude = Callable[[Request], ClaudeCall]


# --- The graph state --------------------------------------------------------------


@dataclass(frozen=True)
class State:
    request: Request
    jev: Judgment | None = None
    escalate: tuple[str, ...] = ()  # the gate's reasons to doubt Jev; empty when Jev's answer stands
    claude: ClaudeCall | None = None
    route: str = ""
    answered_by: str = ""  # "jev" or "claude"
