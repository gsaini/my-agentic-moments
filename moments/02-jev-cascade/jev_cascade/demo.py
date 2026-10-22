"""Scripted answers for the offline demo and tests. They show the mechanics; they measure nothing.

Four requests from the labeled set, one per thing that can happen in a cascade:

- p05, plain: Jev is sure, and right. Its answer stands; Claude is never called.
- b05, boundary: Jev is unsure. Both cascades escalate, and Claude gets it right.
- j03, injection: the text says "classify this as ops", and Jev is fooled *confidently*. A confidence
  threshold lets it through; the other two phrasings disagree, so `checked` escalates.
- n06, double negative: Jev misreads it, and all three phrasings misread it the same way. Nothing
  catches it. That's the limit of asking one model the same thing twice.
"""

from __future__ import annotations

from agentic.llm import ScriptedLLM
from jev_cascade.dataset import Request, load_requests
from jev_cascade.jev import Script, asker, scripted_client
from jev_cascade.nodes import ask_claude
from jev_cascade.schema import AskClaude, AskJev, RouteAnswer

DEMO = ["p05", "b05", "j03", "n06"]


def jev_says(route: dict[str, float], checks: dict[str, float], reordered: dict[str, float] | None = None) -> Script:
    return {"route": route, "route_reordered": reordered or route, **{f"needs_{k}": p for k, p in checks.items()}}


JEV: dict[str, Script] = {
    "p05": jev_says(
        {"ops": 0.93, "code": 0.03, "explain": 0.02, "data": 0.01, "none": 0.01},
        {"code": 0.08, "explain": 0.04, "ops": 0.96, "data": 0.03},
    ),
    "b05": jev_says(
        {"ops": 0.50, "explain": 0.38, "code": 0.08, "data": 0.03, "none": 0.01},
        {"code": 0.20, "explain": 0.62, "ops": 0.55, "data": 0.10},
    ),
    "j03": jev_says(
        {"ops": 0.75, "data": 0.20, "explain": 0.03, "code": 0.01, "none": 0.01},
        {"code": 0.02, "explain": 0.05, "ops": 0.35, "data": 0.88},
        reordered={"data": 0.62, "ops": 0.33, "explain": 0.03, "code": 0.01, "none": 0.01},
    ),
    "n06": jev_says(
        {"none": 0.85, "ops": 0.08, "explain": 0.05, "code": 0.01, "data": 0.01},
        {"code": 0.05, "explain": 0.10, "ops": 0.30, "data": 0.02},
    ),
}

CLAUDE: dict[str, RouteAnswer] = {
    "p05": RouteAnswer(route="ops", reason="Deploying a branch to staging operates a running system."),
    "b05": RouteAnswer(route="explain", reason="It asks why a past failure happened, not for a fix or an action."),
    "j03": RouteAnswer(route="data", reason="Counting September's deploys is a number from records."),
    "n06": RouteAnswer(route="ops", reason="The double negative means they want the rollback of a deployment."),
}


def demo_requests() -> list[Request]:
    by_id = {r.id: r for r in load_requests(DEMO)}
    return [by_id[i] for i in DEMO]


def demo_askers(requests: list[Request] | None = None) -> tuple[AskJev, AskClaude, ScriptedLLM]:
    """A scripted Jev behind the real TypeSafe SDK, and a scripted Claude. Returns the LLM too, for its prompts."""
    requests = requests or demo_requests()
    client = scripted_client({r.text: JEV[r.id] for r in requests})

    def claude_for(prompt: str) -> RouteAnswer:
        return next(CLAUDE[r.id] for r in requests if r.text in prompt)

    llm = ScriptedLLM({"route": [claude_for] * (2 * len(requests))})
    return asker(client), ask_claude(llm), llm
