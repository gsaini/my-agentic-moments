"""Ask each model once per request, then replay every variant and threshold from those answers.

Collecting once makes the comparison paired: when a cascade escalates a request, the Claude answer it
gets is the very one Claude-only gave. Differences between variants come from the routing rule, not
from sampling noise, and sweeping the threshold costs nothing.
"""

from __future__ import annotations

import dataclasses
import json
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from typesafe_sdk import TypeSafeError

from agentic.llm import PRICES, LLMError, Usage
from jev_cascade.dataset import TRAPS, Request
from jev_cascade.graphs import DEFAULT_THRESHOLD, DESCRIPTIONS, build
from jev_cascade.jev import cost_usd
from jev_cascade.nodes import noul_conflict
from jev_cascade.schema import AskClaude, AskJev, ClaudeCall, Judgment, RouteAnswer, State

SWEEP = (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


@dataclass(frozen=True)
class Record:
    """Both models' answers to one request (None where the call failed)."""

    request: Request
    jev: Judgment | None = None
    claude: ClaudeCall | None = None
    error: str = ""


@dataclass(frozen=True)
class Outcome:
    """One request through one variant."""

    request: Request
    route: str = ""
    answered_by: str = ""
    escalate: tuple[str, ...] = ()
    jev: Judgment | None = None  # set only when the variant asked Jev
    claude: ClaudeCall | None = None  # set only when the variant asked Claude
    error: str = ""

    @property
    def correct(self) -> bool:
        return not self.error and self.route == self.request.route


class Unanswered(Exception):
    """A replay needed an answer that was never recorded (that call failed)."""


def collect(
    requests: list[Request], ask_jev: AskJev, ask_claude: AskClaude, *, out: Path | None = None
) -> list[Record]:
    """One Jev request and one Claude call per labeled request. Written as they arrive, so a crash loses nothing."""
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("", encoding="utf-8")
    records = []
    for request in requests:
        jev = claude = None
        errors = []
        try:
            jev = ask_jev(request)
        except TypeSafeError as exc:  # rate limits, timeouts, outages — recorded, not fatal
            errors.append(f"Jev: {type(exc).__name__}: {exc}")
        try:
            claude = ask_claude(request)
        except LLMError as exc:  # a refusal or an unparseable reply
            errors.append(f"Claude: {exc}")
        record = Record(request, jev, claude, "; ".join(errors))
        records.append(record)
        if out:
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(_dump(record)) + "\n")
    return records


def replay(records: list[Record], variant: str, threshold: float = DEFAULT_THRESHOLD) -> list[Outcome]:
    """Run every request through a variant's graph, answering from the records — no model calls."""
    jev_answers = {r.request.id: r.jev for r in records}
    claude_answers = {r.request.id: r.claude for r in records}
    graph = build(variant, _recorded(jev_answers, "Jev"), _recorded(claude_answers, "Claude"), threshold)
    outcomes = []
    for record in records:
        try:
            state, _ = graph.run(State(request=record.request))
        except Unanswered as exc:
            outcomes.append(Outcome(record.request, error=str(exc)))
            continue
        outcomes.append(
            Outcome(record.request, state.route, state.answered_by, state.escalate, state.jev, state.claude)
        )
    return outcomes


def _recorded(answers: dict, who: str) -> Callable[[Request], object]:
    def ask(request: Request):
        if answers.get(request.id) is None:
            raise Unanswered(f"no {who} answer recorded for {request.id}")
        return answers[request.id]

    return ask


# --- Scoring ----------------------------------------------------------------------


def summarize(outcomes: list[Outcome]) -> dict:
    accepted = [o for o in outcomes if o.answered_by == "jev"]
    escalated = [o for o in outcomes if o.answered_by == "claude" and o.jev is not None]
    latencies = sorted(_latency(o) for o in outcomes if not o.error)
    return {
        "n": len(outcomes),
        "correct": sum(o.correct for o in outcomes),
        "errors": sum(bool(o.error) for o in outcomes),
        "claude_calls": sum(o.claude is not None for o in outcomes),
        "slipped": sum(not o.correct for o in accepted),  # Jev was wrong and nobody checked
        "rescued": sum(o.correct and o.jev.route != o.request.route for o in escalated),
        "spoiled": sum(not o.correct and o.jev.route == o.request.route for o in escalated),
        "cost": total_cost(outcomes),
        "p50": statistics.median(latencies) if latencies else 0.0,
        "p95": latencies[max(0, round(0.95 * len(latencies)) - 1)] if latencies else 0.0,
    }


def total_cost(outcomes: list[Outcome]) -> float | None:
    """Estimated $ at list prices; None when a model has no known price (e.g. a scripted one)."""
    total = 0.0
    for o in outcomes:
        if o.jev:
            if not o.jev.model.startswith("jev-"):
                return None
            total += cost_usd(o.jev.input_tokens)
        if o.claude:
            if o.claude.model not in PRICES:
                return None
            p_in, p_out = PRICES[o.claude.model]
            total += (o.claude.usage.input_tokens * p_in + o.claude.usage.output_tokens * p_out) / 1e6
    return total


def _latency(o: Outcome) -> float:
    return (o.jev.latency_ms if o.jev else 0.0) + (o.claude.latency_ms if o.claude else 0.0)


# Rows that can't happen in a variant: Jev-only never escalates, Claude-only never asks Jev.
_NOT_APPLICABLE = {"jev": {"rescued", "spoiled"}, "claude": {"slipped", "rescued", "spoiled"}}


def scoreboard(results: dict[str, list[Outcome]]) -> str:
    stats = {v: summarize(o) for v, o in results.items()}
    cols = list(results)

    def row(label: str, cell) -> str:
        return f"| {label} | {' | '.join(cell(stats[v]) for v in cols)} |"

    def count(key: str):
        return lambda s: "–" if key in _NOT_APPLICABLE.get(s["variant"], ()) else str(s[key])

    for v in cols:
        stats[v]["variant"] = v
    lines = [f"| | {' | '.join(f'`{v}`' for v in cols)} |", "|---|" + "|".join(":-:" for _ in cols) + "|"]
    lines.append(row("**correct**", lambda s: f"**{s['correct']}/{s['n']}**"))
    lines.append(row("answered by Claude", count("claude_calls")))
    lines.append(row("Jev wrong, answer stood", count("slipped")))
    lines.append(row("Jev wrong, Claude fixed it", count("rescued")))
    lines.append(row("Jev right, Claude got it wrong", count("spoiled")))
    lines.append(row("est. cost", lambda s: "n/a" if s["cost"] is None else f"${s['cost']:.4f}"))
    lines.append(row("latency p50 / p95", lambda s: f"{s['p50']:,.0f} / {s['p95']:,.0f} ms"))
    if any(s["errors"] for s in stats.values()):
        lines.append(row("failed calls", count("errors")))
    return "\n".join(lines)


def doubt_table(records: list[Record], threshold: float = DEFAULT_THRESHOLD) -> str:
    """How often each reason to doubt Jev fires on its wrong answers (catches) and on its right ones (wasted calls)."""
    answered = [r for r in records if r.jev is not None]
    wrong = [r.jev for r in answered if r.jev.route != r.request.route]
    right = [r.jev for r in answered if r.jev.route == r.request.route]
    signals = {
        f"confidence < {threshold}": lambda j: j.confidence < threshold,
        "reordering the options changes the answer": lambda j: j.reordered != j.route,
        "the Nouls contradict the Choice": lambda j: bool(noul_conflict(j)),
    }

    def any_of(j: Judgment) -> bool:
        return any(fires(j) for fires in signals.values())

    lines = [
        f"| doubt | fires when Jev was wrong (n={len(wrong)}) | fires when Jev was right (n={len(right)}) |",
        "|---|:-:|:-:|",
    ]
    for label, fires in signals.items():
        lines.append(f"| {label} | {sum(map(fires, wrong))} | {sum(map(fires, right))} |")
    lines.append(f"| **any of them** (`checked`) | **{sum(map(any_of, wrong))}** | **{sum(map(any_of, right))}** |")
    lines.append(f"| none: the wrong answer stands | {sum(not any_of(j) for j in wrong)} | |")
    return "\n".join(lines)


def sweep(records: list[Record]) -> str:
    lines = [
        "| threshold | `cascade`: correct · to Claude | `checked`: correct · to Claude |",
        "|---|:-:|:-:|",
    ]
    for tau in SWEEP:
        cells = []
        for variant in ("cascade", "checked"):
            s = summarize(replay(records, variant, tau))
            cells.append(f"{s['correct']}/{s['n']} · {s['claude_calls']}")
        lines.append(f"| {tau:.2f} | {' | '.join(cells)} |")
    return "\n".join(lines)


def by_trap(results: dict[str, list[Outcome]]) -> str:
    cols = list(results)
    lines = [f"| trap | n | {' | '.join(f'`{v}`' for v in cols)} |", "|---|:-:|" + "|".join(":-:" for _ in cols) + "|"]
    for trap in TRAPS:
        idx = [i for i, o in enumerate(next(iter(results.values()))) if o.request.trap == trap]
        if idx:
            cells = [str(sum(results[v][i].correct for i in idx)) for v in cols]
            lines.append(f"| {trap} | {len(idx)} | {' | '.join(cells)} |")
    return "\n".join(lines)


def report(records: list[Record], threshold: float = DEFAULT_THRESHOLD) -> str:
    results = {variant: replay(records, variant, threshold) for variant in DESCRIPTIONS}
    jev_model = next((r.jev.model for r in records if r.jev), "?")
    claude_model = next((r.claude.model for r in records if r.claude), "?")
    return "\n\n".join([
        f"Jev `{jev_model}` · Claude `{claude_model}` · threshold {threshold} · {len(records)} requests",
        scoreboard(results),
        "**Why the gate doubted Jev**\n\n" + doubt_table(records, threshold),
        "**Threshold sweep** (replayed from the same answers — no new calls)\n\n" + sweep(records),
        "**Correct, by trap**\n\n" + by_trap(results),
    ])  # fmt: skip


# --- Saving and loading -----------------------------------------------------------


def _dump(record: Record) -> dict:
    claude = None
    if record.claude:
        claude = {**dataclasses.asdict(record.claude), "answer": record.claude.answer.model_dump()}
    jev = dataclasses.asdict(record.jev) if record.jev else None
    return {"id": record.request.id, "text": record.request.text, "jev": jev, "claude": claude, "error": record.error}


def load(path: Path, requests: list[Request]) -> list[Record]:
    """Recorded answers, joined to the current labels by id — so a corrected label needs no new calls."""
    current = {r.id: r for r in requests}
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        request = current.get(raw["id"])
        if request is None or request.text != raw["text"]:
            raise ValueError(f"{raw['id']}: the request changed since these answers were recorded; collect again")
        claude = raw["claude"]
        if claude:
            claude = ClaudeCall(RouteAnswer(**claude["answer"]), Usage(**claude["usage"]), claude["model"],
                                claude["latency_ms"])  # fmt: skip
        records.append(Record(request, Judgment(**raw["jev"]) if raw["jev"] else None, claude, raw["error"]))
    return records
