"""Four graphs from the same nodes. The two cascades share their wiring; only the gate's rule differs.

jev      jev → finalize                                   (System One only)
claude   claude → finalize                                (System Two only)
cascade  jev → gate ⟲ claude                              (escalate when Jev's confidence is low)
checked  jev → gate ⟲ claude                              (... or when Jev's three phrasings disagree)
"""

from __future__ import annotations

from agentic.graph import END, Graph
from jev_cascade import nodes as n
from jev_cascade.schema import AskClaude, AskJev, State

DESCRIPTIONS = {
    "jev": "System One only — Jev answers everything",
    "claude": "System Two only — Claude answers everything",
    "cascade": "Jev first; Claude when Jev's confidence is below the threshold",
    "checked": "Jev first; Claude when Jev is unsure or its three phrasings disagree",
}

DEFAULT_THRESHOLD = 0.6  # TypeSafe's confidence-gated routing example uses 0.6 as its floor


def build(variant: str, ask_jev: AskJev, ask_claude: AskClaude, threshold: float = DEFAULT_THRESHOLD) -> Graph[State]:
    if variant not in DESCRIPTIONS:
        raise ValueError(f"unknown variant {variant!r}; choose from {', '.join(DESCRIPTIONS)}")
    g: Graph[State] = Graph(entry="claude" if variant == "claude" else "jev")
    if variant == "jev":
        g.node("jev", n.jev(ask_jev)).edge("jev", "finalize")
    elif variant == "claude":
        g.node("claude", n.claude(ask_claude)).edge("claude", "finalize")
    else:
        g.node("jev", n.jev(ask_jev)).node("gate", n.gate(threshold, cross_check=variant == "checked"))
        g.node("claude", n.claude(ask_claude))
        g.edge("jev", "gate").route("gate", n.escalate, ("claude", "finalize")).edge("claude", "finalize")
    g.node("finalize", n.finalize).edge("finalize", END)
    return g.compile()
