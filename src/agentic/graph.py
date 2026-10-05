"""A tiny graph runtime — the core of graph engineering in ~120 lines.

An agent as an explicit graph:
- **State** is an immutable dataclass. Nodes never mutate it; they return the
  fields they changed, and the runtime builds the next state.
- **Nodes** are plain functions `state -> dict of updates`.
- **Edges** say what runs next: fixed (`a -> b`) or conditional (a router
  function that looks at the state and names the next node).
- **Cycles are allowed** (that's how a critique loop loops) and **bounded**:
  every run has a step limit.
- **Every step is checkpointed** — `(step, node, state)` — so a run can be
  inspected, replayed, or resumed from any point.

LangGraph users: this is `StateGraph`, `add_node`, `add_edge`,
`add_conditional_edges`, `END`, and a checkpointer, without the framework.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

S = TypeVar("S")
END = "__end__"


class GraphError(Exception):
    """The graph is wired wrong (caught at compile time)."""


class StepLimit(Exception):
    """A run exceeded its step limit — usually a cycle that never exits."""


@dataclass(frozen=True)
class Checkpoint(Generic[S]):
    step: int
    node: str  # the node that just ran
    state: S
    next: str  # the node that runs next (END when finished)


@dataclass
class Graph(Generic[S]):
    entry: str
    nodes: dict[str, Callable[[S], dict[str, Any]]] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)
    routers: dict[str, tuple[Callable[[S], str], tuple[str, ...]]] = field(default_factory=dict)

    def node(self, name: str, fn: Callable[[S], dict[str, Any]]) -> Graph[S]:
        self.nodes[name] = fn
        return self

    def edge(self, source: str, target: str) -> Graph[S]:
        self.edges[source] = target
        return self

    def route(self, source: str, router: Callable[[S], str], targets: tuple[str, ...]) -> Graph[S]:
        """A conditional edge. `targets` lists every node the router may return."""
        self.routers[source] = (router, targets)
        return self

    def compile(self) -> Graph[S]:
        """Check the wiring before anything runs: a wrong edge should fail here, not mid-run."""
        known = set(self.nodes) | {END}
        if self.entry not in self.nodes:
            raise GraphError(f"entry node {self.entry!r} is not defined")
        for name in self.nodes:
            if (name in self.edges) == (name in self.routers):
                raise GraphError(f"node {name!r} needs exactly one outgoing edge or router")
        for source, target in self.edges.items():
            if target not in known:
                raise GraphError(f"edge {source!r} -> {target!r}: unknown target")
        for source, (_, targets) in self.routers.items():
            for target in targets:
                if target not in known:
                    raise GraphError(f"router on {source!r} may return unknown node {target!r}")
        if END not in self._reachable():
            raise GraphError("END is not reachable: every run would hit the step limit")
        return self

    def _reachable(self) -> set[str]:
        seen, todo = set(), [self.entry]
        while todo:
            name = todo.pop()
            if name in seen or name == END:
                seen.add(name)
                continue
            seen.add(name)
            todo.extend([self.edges[name]] if name in self.edges else list(self.routers[name][1]))
        return seen

    def run(
        self,
        state: S,
        *,
        start: str | None = None,
        max_steps: int = 30,
        on_step: Callable[[Checkpoint[S]], None] | None = None,
    ) -> tuple[S, list[Checkpoint[S]]]:
        """Run from `start` (default: the entry node) until END. Returns the final state and every checkpoint."""
        checkpoints: list[Checkpoint[S]] = []
        current = start or self.entry
        for step in range(1, max_steps + 1):
            update = self.nodes[current](state)
            state = dataclasses.replace(state, **update)  # type: ignore[type-var]
            nxt = self._next(current, state)
            checkpoint = Checkpoint(step, current, state, nxt)
            checkpoints.append(checkpoint)
            if on_step:
                on_step(checkpoint)
            if nxt == END:
                return state, checkpoints
            current = nxt
        raise StepLimit(f"no END after {max_steps} steps (last node: {current!r})")

    def resume(self, checkpoint: Checkpoint[S], **kwargs: Any) -> tuple[S, list[Checkpoint[S]]]:
        """Continue a run from a saved checkpoint (durable execution, in one line)."""
        if checkpoint.next == END:
            return checkpoint.state, []
        return self.run(checkpoint.state, start=checkpoint.next, **kwargs)

    def _next(self, current: str, state: S) -> str:
        if current in self.edges:
            return self.edges[current]
        router, targets = self.routers[current]
        target = router(state)
        if target not in targets:
            raise GraphError(f"router on {current!r} returned {target!r}, not one of {targets}")
        return target

    def mermaid(self) -> str:
        """The graph as a Mermaid flowchart (GitHub renders these in Markdown)."""
        lines = ["flowchart LR", f"    START(( )) --> {self.entry}"]
        for source, target in self.edges.items():
            lines.append(f"    {source} --> {_m(target)}")
        for source, (_, targets) in self.routers.items():
            for target in targets:
                lines.append(f"    {source} -.-> {_m(target)}")
        return "\n".join(lines)


def _m(name: str) -> str:
    return "END(( ))" if name == END else name
