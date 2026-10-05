"""The nodes. Each is a function `State -> dict of updates`; the graph wires them.

Every model call is a fresh, single-turn conversation: nodes pass artifacts
(code, test results, issues) through the state, not transcripts. That keeps each
node's context small and focused — and keeps the critic from seeing, and
deferring to, the author's reasoning.
"""

from __future__ import annotations

from collections.abc import Callable

from agentic.llm import LLM
from critique_graph.sandbox import run_probes, run_tests
from critique_graph.schema import Critique, Draft, Issue, Probe, ProbingCritique, State

AUTHOR = """You write small, correct Python functions from a spec.
Return the complete module. Use only the standard library."""

CRITIC = """You review Python code that someone else wrote, against its spec.
Find real defects: wrong results, missed edge cases, crashes, spec violations.
Every issue must cite evidence — a failing test, a probe result, or a concrete input
and what the code does with it. No style nits, no speculation without evidence.
Say 'pass' only if you would ship the code as is."""

PROBE_HINT = """Also propose probes: up to 6 single calls with the exact result the spec requires,
aimed at the edge cases most likely to be wrong. They will be executed against the code."""

Node = Callable[[State], dict]


def draft(llm: LLM) -> Node:
    def node(s: State) -> dict:
        prompt = f"Spec:\n{s.task.spec}\n\nThese tests must pass:\n```python\n{s.task.visible_tests}\n```"
        out, usage = llm.ask(role="draft", system=AUTHOR, prompt=prompt, schema=Draft)
        return {"code": out.code, "approach": out.approach, "round": 1, "usage": s.usage + usage}

    return node


def check(s: State) -> dict:
    """Run the visible tests. Earlier probes are re-run too, so a fix can't silently undo another."""
    result = run_tests(s.code, s.task.visible_tests)
    if s.probes:
        rerun = run_probes(s.code, [_as_probe(p) for p in s.probes if p.valid], s.task.function)
        return {"checks": result, "probes": tuple(rerun)}
    return {"checks": result}


def critique(llm: LLM, *, grounded: bool, probing: bool = False) -> Node:
    schema = ProbingCritique if probing else Critique

    def node(s: State) -> dict:
        parts = [f"Spec:\n{s.task.spec}", f"Code:\n```python\n{s.code}\n```"]
        if grounded and s.checks:
            parts.append(_evidence(s))
        if probing:
            parts.append(PROBE_HINT)
        out, usage = llm.ask(role="critique", system=CRITIC, prompt="\n\n".join(parts), schema=schema)
        return {"critique": out, "usage": s.usage + usage}

    return node


def probe(s: State) -> dict:
    """Run the critic's probes. A suspicion becomes a fact — or is disproved."""
    assert isinstance(s.critique, ProbingCritique)
    results = run_probes(s.code, s.critique.probes, s.task.function)
    seen = {(p.call, p.expected) for p in s.probes}
    return {"probes": s.probes + tuple(r for r in results if (r.call, r.expected) not in seen)}


def gate(s: State) -> dict:
    """Critique the critique, with code instead of another opinion.

    - Issues without evidence are dropped: a vague critique is noise.
    - A failing test or probe always means 'revise', whatever the critic said.
    - A failing probe becomes a blocker issue with the evidence spelled out.
    - 'Revise' with nothing actionable left becomes 'pass'.
    """
    assert s.critique is not None and s.checks is not None
    kept = [i for i in s.critique.issues if i.evidence.strip()]
    dropped = len(s.critique.issues) - len(kept)
    failing = [p for p in s.probes if p.valid and not p.passed]
    kept += [
        Issue(
            severity="blocker",
            problem=f"{p.call} returns {p.actual}",
            evidence=f"probe expected {p.expected}",
            fix="Make the code return the expected value for this input.",
        )  # fmt: skip
        for p in failing
    ]
    verdict = s.critique.verdict
    if not s.checks.ok or failing:
        verdict = "revise"
    elif verdict == "revise" and not kept:
        verdict = "pass"
    gated = Critique(verdict=verdict, issues=kept)
    note = {"dropped_vague": dropped, "probes_failed": len(failing), "overrode": verdict != s.critique.verdict}
    return {"critique": gated, "history": s.history[:-1] + ({**s.history[-1], **note},) if s.history else (note,)}


def record(s: State) -> dict:
    """Append one summary line per critique round (what the trace and scoreboard show)."""
    assert s.critique is not None
    entry = {
        "round": s.round,
        "visible": f"{s.checks.passed}/{s.checks.passed + s.checks.failed}" if s.checks else "not run",
        "verdict": s.critique.verdict,
        "issues": len(s.critique.issues),
    }
    return {"history": s.history + (entry,)}


def revise(llm: LLM) -> Node:
    def node(s: State) -> dict:
        assert s.critique is not None
        issues = "\n".join(
            f"- [{i.severity}] {i.problem} (evidence: {i.evidence}) → fix: {i.fix}" for i in s.critique.issues
        )
        parts = [
            f"Spec:\n{s.task.spec}",
            f"Current code:\n```python\n{s.code}\n```",
            f"Review findings:\n{issues or '(none)'}",
        ]
        if s.checks and not s.checks.ok:
            parts.append(_evidence(s))
        prompt = "\n\n".join(parts) + "\n\nReturn the corrected, complete module."
        out, usage = llm.ask(role="revise", system=AUTHOR, prompt=prompt, schema=Draft)
        return {"code": out.code, "approach": out.approach, "round": s.round + 1, "usage": s.usage + usage}

    return node


def decide(max_rounds: int) -> Callable[[State], str]:
    """Router: loop back to `revise`, or stop."""

    def router(s: State) -> str:
        return "revise" if not stop_reason(s, max_rounds) else "finalize"

    return router


def stop_reason(s: State, max_rounds: int) -> str:
    if s.critique is None:
        return "single shot"
    if s.critique.verdict == "pass":
        return "critic passed"
    if s.round >= max_rounds:
        return "round budget"
    return ""


def finalize(max_rounds: int) -> Node:
    def node(s: State) -> dict:
        return {"stop_reason": stop_reason(s, max_rounds) or "single shot"}

    return node


def _evidence(s: State) -> str:
    assert s.checks is not None
    lines = [f"Visible tests: {s.checks.passed} passed, {s.checks.failed} failed."]
    if s.checks.output:
        lines.append(s.checks.output)
    if s.probes:
        lines.append("Probes run so far:")
        lines += [
            f"- {p.call} → {p.actual} (expected {p.expected}) {'✓' if p.passed else '✗'}" for p in s.probes if p.valid
        ]
    return "\n".join(lines)


def _as_probe(result) -> Probe:
    return Probe(call=result.call, expected=result.expected)
