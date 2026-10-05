"""A scripted model for the offline demo and tests. It shows the mechanics; it measures nothing.

The story: the first draft passes every visible test but mishandles 40, 90, 400
and 900. The critic, too lenient, says "pass" — but the probes it proposes expose
the bug, and the gate overrides its verdict. One vague issue is dropped.
"""

from __future__ import annotations

from agentic.llm import ScriptedLLM
from critique_graph.schema import Draft, Issue, Probe, ProbingCritique

BUGGY = """def to_roman(n):
    table = [(1000, "M"), (500, "D"), (100, "C"), (50, "L"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for value, symbol in table:
        while n >= value:
            out += symbol
            n -= value
    return out
"""

FIXED = """def to_roman(n):
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 3999:
        raise ValueError("n must be an integer from 1 to 3999")
    table = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
             (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for value, symbol in table:
        count, n = divmod(n, value)
        out.append(symbol * count)
    return "".join(out)
"""

PROBES = [
    Probe(call="to_roman(40)", expected="'XL'"),
    Probe(call="to_roman(1994)", expected="'MCMXCIV'"),
    Probe(call="to_roman(0)", expected="raises ValueError"),
]


def demo_llm() -> ScriptedLLM:
    return ScriptedLLM(
        {
            "draft": [Draft(approach="Greedy over a value table.", code=BUGGY)],
            "critique": [
                ProbingCritique(
                    verdict="pass",  # too lenient: the visible tests pass, so it waves the code through
                    issues=[Issue(severity="minor", problem="Could be more Pythonic.", evidence="", fix="Refactor.")],
                    probes=PROBES,
                ),
                ProbingCritique(
                    verdict="pass", issues=[], probes=[Probe(call="to_roman(3999)", expected="'MMMCMXCIX'")]
                ),
            ],
            "revise": [Draft(approach="Full subtractive table, input validation.", code=FIXED)],
        }
    )
