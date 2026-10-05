from dataclasses import dataclass

import pytest

from agentic.graph import END, Graph, GraphError, StepLimit


@dataclass(frozen=True)
class Counter:
    n: int = 0
    log: tuple[str, ...] = ()


def inc(s: Counter) -> dict:
    return {"n": s.n + 1, "log": s.log + ("inc",)}


def done(s: Counter) -> dict:
    return {"log": s.log + ("done",)}


def loop_graph(limit: int = 3) -> Graph[Counter]:
    g: Graph[Counter] = Graph(entry="inc")
    g.node("inc", inc).node("done", done).edge("done", END)
    g.route("inc", lambda s: "inc" if s.n < limit else "done", ("inc", "done"))
    return g.compile()


def test_cycles_run_until_the_router_exits():
    state, checkpoints = loop_graph(3).run(Counter())
    assert state == Counter(3, ("inc", "inc", "inc", "done"))
    assert [c.node for c in checkpoints] == ["inc", "inc", "inc", "done"]
    assert checkpoints[-1].next == END


def test_checkpoints_are_snapshots():
    _, checkpoints = loop_graph(3).run(Counter())
    assert [c.state.n for c in checkpoints] == [1, 2, 3, 3]  # immutable state: no later step changes an earlier one


def test_resume_from_a_checkpoint_matches_the_full_run():
    graph = loop_graph(5)
    full, checkpoints = graph.run(Counter())
    resumed, _ = graph.resume(checkpoints[1])
    assert resumed == full
    assert graph.resume(checkpoints[-1])[0] == full  # resuming a finished run is a no-op


def test_step_limit_stops_an_endless_cycle():
    with pytest.raises(StepLimit, match="no END after 10 steps"):
        loop_graph(10**9).run(Counter(), max_steps=10)


@pytest.mark.parametrize(
    "wire, message",
    [
        (lambda g: g.node("a", inc).edge("a", "nowhere"), "unknown target"),
        (lambda g: g.node("a", inc), "exactly one outgoing edge"),
        (lambda g: g.node("a", inc).edge("a", END).route("a", lambda s: END, (END,)), "exactly one outgoing edge"),
        (lambda g: g.node("a", inc).route("a", lambda s: "a", ("a", "ghost")), "unknown node"),
        (lambda g: g.node("a", inc).edge("a", "a"), "END is not reachable"),
    ],
)
def test_wiring_mistakes_fail_at_compile_time(wire, message):
    g: Graph[Counter] = Graph(entry="a")
    wire(g)
    with pytest.raises(GraphError, match=message):
        g.compile()


def test_router_returning_an_undeclared_node_fails_loudly():
    g: Graph[Counter] = Graph(entry="a")
    g.node("a", inc).node("b", done).edge("b", END).route("a", lambda s: "c", ("b",))
    with pytest.raises(GraphError, match="returned 'c'"):
        g.compile().run(Counter())


def test_mermaid():
    text = loop_graph().mermaid()
    assert "START(( )) --> inc" in text and "done --> END(( ))" in text
    assert "inc -.-> inc" in text and "inc -.-> done" in text  # conditional edges are dotted
