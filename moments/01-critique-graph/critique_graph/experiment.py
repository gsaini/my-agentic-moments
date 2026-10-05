"""Run tasks × graph variants, grade on hidden tests, and print a scoreboard."""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass
from pathlib import Path

from agentic.graph import Checkpoint, StepLimit
from agentic.llm import LLM, LLMError, Usage
from critique_graph.graphs import build
from critique_graph.sandbox import run_tests
from critique_graph.schema import State
from critique_graph.tasks import Task

# $ per million tokens (input, output) — for estimates only.
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-4-5": (1.00, 5.00)}


@dataclass
class Outcome:
    task: str
    variant: str
    hidden_passed: int
    hidden_total: int
    rounds: int
    usage: Usage
    stop_reason: str
    history: tuple[dict, ...]
    error: str = ""

    @property
    def solved(self) -> bool:
        return not self.error and self.hidden_total > 0 and self.hidden_passed == self.hidden_total


def run_one(task: Task, variant: str, llm: LLM, *, max_rounds: int = 4, trace: Path | None = None) -> Outcome:
    graph = build(variant, llm, max_rounds)
    writer = _trace_writer(trace)
    try:
        state, _ = graph.run(State(task=task), max_steps=60, on_step=writer)
    except (LLMError, StepLimit) as exc:
        return Outcome(task.id, variant, 0, 0, 0, Usage(), "error", (), error=f"{type(exc).__name__}: {exc}")
    hidden = run_tests(state.code, task.hidden_tests)
    return Outcome(task.id, variant, hidden.passed, hidden.passed + hidden.failed, state.round, state.usage,
                   state.stop_reason, state.history)  # fmt: skip


def run_experiment(tasks: list[Task], variants: list[str], make_llm, *, out: Path | None = None, **kw) -> list[Outcome]:
    outcomes = []
    for task in tasks:
        for variant in variants:
            trace = out / f"{task.id}-{variant}.jsonl" if out else None
            outcomes.append(run_one(task, variant, make_llm(), trace=trace, **kw))
    return outcomes


def scoreboard(outcomes: list[Outcome], model: str) -> str:
    tasks = list(dict.fromkeys(o.task for o in outcomes))
    variants = list(dict.fromkeys(o.variant for o in outcomes))
    cell = {(o.task, o.variant): o for o in outcomes}
    lines = [f"| task | {' | '.join(variants)} |", "|---|" + "|".join(":-:" for _ in variants) + "|"]
    for t in tasks:
        row = []
        for v in variants:
            o = cell[(t, v)]
            row.append(
                f"💥 {o.error[:30]}"
                if o.error
                else f"{'✅' if o.solved else '❌'} {o.hidden_passed}/{o.hidden_total} · {o.rounds}r"
            )
        lines.append(f"| {t} | {' | '.join(row)} |")
    solved = [f"**{sum(cell[(t, v)].solved for t in tasks)}/{len(tasks)}**" for v in variants]
    lines.append(f"| **solved (hidden tests)** | {' | '.join(solved)} |")
    usage = {v: sum((cell[(t, v)].usage for t in tasks), Usage()) for v in variants}
    lines.append(f"| model calls | {' | '.join(str(u.calls) for u in usage.values())} |")
    lines.append(
        f"| tokens in / out | {' | '.join(f'{u.input_tokens:,} / {u.output_tokens:,}' for u in usage.values())} |"
    )
    if model in PRICES:
        p_in, p_out = PRICES[model]
        costs = [f"${(u.input_tokens * p_in + u.output_tokens * p_out) / 1e6:.2f}" for u in usage.values()]
        lines.append(f"| est. cost | {' | '.join(costs)} |")
    return "\n".join(lines)


def _trace_writer(path: Path | None):
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")

    def write(cp: Checkpoint[State]) -> None:
        state = dataclasses.asdict(cp.state)
        state.pop("task")  # the task is the same at every step
        if state.get("critique") is not None:
            state["critique"] = cp.state.critique.model_dump()
        record = {"t": round(time.time(), 3), "step": cp.step, "node": cp.node, "next": cp.next, "state": state}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    return write
