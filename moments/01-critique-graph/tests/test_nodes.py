from critique_graph import nodes
from critique_graph.schema import CheckResult, Critique, Issue, ProbeResult, State
from critique_graph.tasks import load_tasks

TASK = load_tasks(["roman"])[0]


def state(**kw) -> State:
    defaults = {"task": TASK, "code": "x", "round": 1, "checks": CheckResult(4, 0), "history": ({"round": 1},)}
    return State(**{**defaults, **kw})


def issue(evidence: str = "to_roman(40) returned 'XXXX'") -> Issue:
    return Issue(severity="major", problem="wrong", evidence=evidence, fix="fix it")


def test_gate_drops_issues_without_evidence():
    out = nodes.gate(state(critique=Critique(verdict="revise", issues=[issue(""), issue()])))
    assert len(out["critique"].issues) == 1 and out["history"][-1]["dropped_vague"] == 1


def test_gate_overrides_a_pass_when_a_probe_fails():
    failing = ProbeResult("to_roman(40)", "'XL'", "'XXXX'", passed=False)
    out = nodes.gate(state(critique=Critique(verdict="pass", issues=[]), probes=(failing,)))
    assert out["critique"].verdict == "revise"
    assert (
        out["critique"].issues[0].severity == "blocker"
        and "to_roman(40) returns 'XXXX'" in out["critique"].issues[0].problem
    )
    assert out["history"][-1]["overrode"] is True


def test_gate_overrides_a_pass_when_visible_tests_fail():
    out = nodes.gate(state(critique=Critique(verdict="pass", issues=[]), checks=CheckResult(3, 1)))
    assert out["critique"].verdict == "revise"


def test_gate_turns_an_empty_revise_into_a_pass():
    out = nodes.gate(state(critique=Critique(verdict="revise", issues=[issue("")])))
    assert out["critique"].verdict == "pass"


def test_router_stops_on_pass_or_budget():
    route = nodes.decide(max_rounds=3)
    assert route(state(critique=Critique(verdict="pass", issues=[]))) == "finalize"
    assert route(state(critique=Critique(verdict="revise", issues=[issue()]), round=2)) == "revise"
    assert route(state(critique=Critique(verdict="revise", issues=[issue()]), round=3)) == "finalize"
    assert nodes.stop_reason(state(critique=Critique(verdict="revise", issues=[issue()]), round=3), 3) == "round budget"
