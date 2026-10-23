"""The nodes. Each is a function `State -> dict of updates`; the graph wires them.

The two model nodes ask through an *asker*, a function from a request to an answer. Handing it the
request and nothing else is the boundary: Claude never sees Jev's answer, so it can't defer to it.
It also lets the experiment swap live calls for recorded answers without the graph noticing.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from agentic.llm import LLM
from jev_cascade.dataset import Request
from jev_cascade.routes import SYSTEM, prompt_for
from jev_cascade.schema import AskClaude, AskJev, ClaudeCall, Judgment, RouteAnswer, State

Node = Callable[[State], dict]


def jev(ask: AskJev) -> Node:
    def node(s: State) -> dict:
        return {"jev": ask(s.request)}

    return node


def gate(threshold: float, *, cross_check: bool) -> Node:
    """Decide, in code, whether Jev's answer stands. Every reason to doubt it is recorded."""

    def node(s: State) -> dict:
        assert s.jev is not None
        return {"escalate": tuple(doubts(s.jev, threshold, cross_check=cross_check))}

    return node


def doubts(j: Judgment, threshold: float, *, cross_check: bool) -> list[str]:
    found = []
    if j.confidence < threshold:
        found.append(f"confidence {j.confidence:.2f} < {threshold}")
    if cross_check:
        if j.reordered != j.route:
            found.append(f"reordering the options changes the answer to {j.reordered}")
        if conflict := noul_conflict(j):
            found.append(conflict)
    return found


def noul_conflict(j: Judgment) -> str:
    """Why the per-specialist Nouls contradict the Choice, or '' when they back it up.

    They back it up when the pick's own Noul says yes and no other Noul is as sure — or, for `none`,
    when no Noul says yes at all.
    """
    yes = [name for name, p in j.checks.items() if p >= 0.5]
    if j.route == "none":
        return f"the Choice says none, but the Nouls say yes to {', '.join(yes)}" if yes else ""
    own = j.checks[j.route]
    if own < 0.5:
        return f"the Choice says {j.route}, but its own Noul says no ({own:.2f})"
    rival, p = max(((name, p) for name, p in j.checks.items() if name != j.route), key=lambda kv: kv[1])
    if p >= own:
        return f"the Choice says {j.route} ({own:.2f}), but the {rival} Noul is at least as sure ({p:.2f})"
    return ""


def escalate(s: State) -> str:
    """Router: to Claude when the gate found any doubt, otherwise Jev's answer stands."""
    return "claude" if s.escalate else "finalize"


def claude(ask: AskClaude) -> Node:
    def node(s: State) -> dict:
        return {"claude": ask(s.request)}

    return node


def finalize(s: State) -> dict:
    if s.claude is not None:
        return {"route": s.claude.answer.route, "answered_by": "claude"}
    assert s.jev is not None
    return {"route": s.jev.route, "answered_by": "jev"}


def ask_claude(llm: LLM) -> AskClaude:
    """A fresh, single-turn call per request: the route definitions and the request, nothing else."""

    def ask(request: Request) -> ClaudeCall:
        started = time.perf_counter()
        answer, usage = llm.ask(role="route", system=SYSTEM, prompt=prompt_for(request.text), schema=RouteAnswer)
        return ClaudeCall(answer, usage, llm.name, (time.perf_counter() - started) * 1000)

    return ask
