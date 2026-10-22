from typing import get_args

import pytest

from agentic.llm import Usage
from jev_cascade.dataset import Request
from jev_cascade.demo import demo_askers, demo_requests
from jev_cascade.experiment import collect, replay, summarize
from jev_cascade.graphs import DESCRIPTIONS, build
from jev_cascade.nodes import doubts, noul_conflict
from jev_cascade.routes import CHECKS, ROUTES, SYSTEM, Route, prompt_for
from jev_cascade.schema import ClaudeCall, Judgment, RouteAnswer, State

REQUEST = Request("x", "Restart the search service.", route="ops")


def judged(route="ops", confidence=0.9, reordered=None, **checks) -> Judgment:
    base = {"code": 0.1, "explain": 0.1, "ops": 0.1, "data": 0.1}
    return Judgment(route, {route: 1.0}, confidence, reordered or route, {**base, **checks}, "jev-1.13.0", 100, 90.0)


def counting(answer):
    calls = []

    def ask(request):
        calls.append(request)
        return answer

    return ask, calls


CLAUDE = ClaudeCall(RouteAnswer(route="ops", reason="r"), Usage(1, 500, 300), "claude-opus-5-5", 2000.0)


def test_one_definition_of_the_routes():
    assert list(ROUTES) == list(get_args(Route))  # Claude's schema and Jev's Choice can't drift apart
    assert set(CHECKS) == set(ROUTES) - {"none"}  # a Noul per specialist; `none` is "no Noul says yes"
    assert all(f"- {name}: {text}" in SYSTEM for name, text in ROUTES.items())  # Claude reads the same definitions


@pytest.mark.parametrize("variant", list(DESCRIPTIONS))
def test_every_variant_compiles(variant):
    assert build(variant, *demo_askers()[:2]).mermaid().startswith("flowchart LR")


def test_single_model_variants_never_call_the_other_model():
    ask_jev, jev_calls = counting(judged())
    ask_claude, claude_calls = counting(CLAUDE)
    state, _ = build("jev", ask_jev, ask_claude).run(State(request=REQUEST))
    assert (state.answered_by, len(jev_calls), len(claude_calls)) == ("jev", 1, 0)
    state, _ = build("claude", ask_jev, ask_claude).run(State(request=REQUEST))
    assert (state.answered_by, len(jev_calls), len(claude_calls)) == ("claude", 1, 1)


@pytest.mark.parametrize(
    ("judgment", "cascade", "checked"),
    [
        (judged(ops=0.9), "jev", "jev"),  # sure, and every phrasing agrees
        (judged(confidence=0.4, ops=0.9), "claude", "claude"),  # unsure
        (judged(reordered="data", ops=0.9), "jev", "claude"),  # reordering the options flips it
        (judged(ops=0.3), "jev", "claude"),  # its own Noul says no
        (judged(ops=0.7, data=0.7), "jev", "claude"),  # a rival Noul is just as sure
        (judged(route="none"), "jev", "jev"),  # none, and no Noul says yes
        (judged(route="none", code=0.8), "jev", "claude"),  # none, but a Noul says yes
    ],
)
def test_who_answers(judgment, cascade, checked):
    for variant, expected in (("cascade", cascade), ("checked", checked)):
        state, _ = build(variant, lambda r: judgment, lambda r: CLAUDE).run(State(request=REQUEST))
        assert state.answered_by == expected, (variant, state.escalate)
        assert bool(state.escalate) == (expected == "claude")  # every escalation says why


def test_doubts_name_every_reason():
    j = judged(confidence=0.3, reordered="data", ops=0.2)
    assert doubts(j, 0.6, cross_check=False) == ["confidence 0.30 < 0.6"]
    assert doubts(j, 0.6, cross_check=True) == [
        "confidence 0.30 < 0.6",
        "reordering the options changes the answer to data",
        "the Choice says ops, but its own Noul says no (0.20)",
    ]
    assert noul_conflict(judged(ops=0.9)) == ""


def test_claude_sees_the_request_and_the_definitions_nothing_else():
    requests = demo_requests()
    ask_jev, ask_claude, llm = demo_askers(requests)
    for request in requests:
        build("checked", ask_jev, ask_claude).run(State(request=request))
    prompts = [prompt for role, prompt in llm.prompts if role == "route"]
    assert len(prompts) == 2  # only the two requests `checked` escalates
    assert set(prompts) <= {prompt_for(r.text) for r in requests}  # exactly the request: no Jev answer, no doubts


def test_the_demo_story():
    requests = demo_requests()
    records = collect(requests, *demo_askers(requests)[:2])
    stats = {v: summarize(replay(records, v)) for v in DESCRIPTIONS}
    assert [stats[v]["correct"] for v in DESCRIPTIONS] == [1, 4, 2, 3]
    assert [stats[v]["claude_calls"] for v in DESCRIPTIONS] == [0, 4, 1, 2]
    # The injected request slips past the confidence gate; the cross-check catches it.
    # The double negative fools every phrasing at once, so it slips past both.
    assert (stats["cascade"]["slipped"], stats["checked"]["slipped"]) == (2, 1)
