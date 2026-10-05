"""Four graphs from the same nodes. Only the wiring changes.

G0  draft → finalize                                      (no critique)
G1  draft → critique ⟲ revise                             (self-critique: no execution feedback)
G2  draft → check → critique ⟲ revise → check             (grounded in the visible tests)
G3  draft → check → critique → probe → gate ⟲ revise      (the critic's suspicions are executed,
                                                            and the critique itself is checked)
"""

from __future__ import annotations

from agentic.graph import END, Graph
from agentic.llm import LLM
from critique_graph import nodes as n
from critique_graph.schema import State

DESCRIPTIONS = {
    "G0": "single shot — no critique",
    "G1": "self-critique — a critic that can only read the code",
    "G2": "grounded critique — the critic sees visible test results",
    "G3": "probing critique + gate — the critic's suspicions are run, and the critique itself is checked",
}


def build(variant: str, llm: LLM, max_rounds: int = 4) -> Graph[State]:
    g: Graph[State] = Graph(entry="draft")
    g.node("draft", n.draft(llm)).node("finalize", n.finalize(max_rounds)).edge("finalize", END)
    route = (n.decide(max_rounds), ("revise", "finalize"))

    if variant == "G0":
        g.edge("draft", "finalize")
    elif variant == "G1":
        g.node("critique", n.critique(llm, grounded=False)).node("record", n.record).node("revise", n.revise(llm))
        g.edge("draft", "critique").edge("critique", "record").route("record", *route).edge("revise", "critique")
    elif variant == "G2":
        g.node("check", n.check).node("critique", n.critique(llm, grounded=True))
        g.node("record", n.record).node("revise", n.revise(llm))
        g.edge("draft", "check").edge("check", "critique").edge("critique", "record")
        g.route("record", *route).edge("revise", "check")
    elif variant == "G3":
        g.node("check", n.check).node("critique", n.critique(llm, grounded=True, probing=True))
        g.node("probe", n.probe).node("record", n.record).node("gate", n.gate).node("revise", n.revise(llm))
        g.edge("draft", "check").edge("check", "critique").edge("critique", "probe").edge("probe", "record")
        g.edge("record", "gate").route("gate", *route).edge("revise", "check")
    else:
        raise ValueError(f"unknown variant {variant!r}; choose from {', '.join(DESCRIPTIONS)}")
    return g.compile()
