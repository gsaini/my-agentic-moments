"""`critique-graph` — run the moment's experiment, one run, a demo, or print a graph."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from agentic.llm import DEFAULT_MODEL, ClaudeLLM, has_credentials
from critique_graph.demo import demo_llm
from critique_graph.experiment import run_experiment, run_one, scoreboard
from critique_graph.graphs import DESCRIPTIONS, build
from critique_graph.tasks import load_tasks

NO_CREDENTIALS = "No Anthropic credentials found. Set ANTHROPIC_API_KEY (or run `ant auth login`), then try again."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="critique-graph", description="Moment 01: critique an agent with a graph.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("graph", help="print a variant as a Mermaid diagram")
    g.add_argument("variant", choices=list(DESCRIPTIONS))

    d = sub.add_parser("demo", help="offline walkthrough of G3 with a scripted model (no API key, nothing measured)")
    d.add_argument("--out", type=Path, default=Path("runs/demo"))

    r = sub.add_parser("run", help="run one task through one variant with Claude")
    r.add_argument("task")
    r.add_argument("--variant", default="G3", choices=list(DESCRIPTIONS))
    _model_args(r)

    e = sub.add_parser("experiment", help="every task × every variant with Claude; prints the scoreboard")
    e.add_argument("--variants", default=",".join(DESCRIPTIONS))
    e.add_argument("--tasks", help="comma-separated task ids (default: all)")
    e.add_argument("--yes", action="store_true", help="confirm the real API calls")
    _model_args(e)

    args = parser.parse_args(argv)
    if args.cmd == "graph":
        print(build(args.variant, demo_llm()).mermaid())
        return 0
    if args.cmd == "demo":
        task = load_tasks(["roman"])[0]
        outcome = run_one(task, "G3", demo_llm(), trace=args.out / "roman-G3.jsonl")
        print("Offline demo — a scripted model, to show the mechanics. Nothing here is a measurement.\n")
        for line in outcome.history:
            gate = []
            if line.get("probes_failed"):
                gate.append(f"{line['probes_failed']} of its probes failed")
            if line.get("dropped_vague"):
                gate.append(f"dropped {line['dropped_vague']} issue(s) with no evidence")
            if line.get("overrode"):
                gate.append("overrode the verdict")
            print(f"  round {line['round']}: visible tests {line['visible']}; critic said {line['verdict']!r} "
                  f"with {line['issues']} issue(s)" + (f" → gate: {', '.join(gate)}" if gate else ""))  # fmt: skip
        print(f"\nStopped: {outcome.stop_reason}. Hidden tests: {outcome.hidden_passed}/{outcome.hidden_total}.")
        print(f"Checkpoints: {args.out / 'roman-G3.jsonl'}")
        return 0

    if not has_credentials():
        print(NO_CREDENTIALS)
        return 2
    if args.cmd == "run":
        task = load_tasks([args.task])[0]
        out = Path("runs") / time.strftime("%Y%m%d-%H%M%S")
        o = run_one(
            task, args.variant, ClaudeLLM(args.model, effort=args.effort), trace=out / f"{task.id}-{args.variant}.jsonl"
        )
        print(f"{task.id} · {args.variant}: hidden {o.hidden_passed}/{o.hidden_total}, {o.rounds} round(s), "
              f"{o.usage.calls} calls, stopped: {o.stop_reason}. {o.error}\nCheckpoints: {out}")  # fmt: skip
        return 0

    variants = [v.strip() for v in args.variants.split(",")]
    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)
    if not args.yes:
        print(f"This runs {len(tasks) * len(variants)} graphs against {args.model}. "
              "Try one first (`critique-graph run roman`), then add --yes.")  # fmt: skip
        return 2
    out = Path("runs") / time.strftime("%Y%m%d-%H%M%S")
    outcomes = run_experiment(tasks, variants, lambda: ClaudeLLM(args.model, effort=args.effort), out=out)
    board = scoreboard(outcomes, args.model)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scoreboard.md").write_text(f"Model: `{args.model}` · effort `{args.effort}`\n\n{board}\n", encoding="utf-8")
    print(f"{board}\n\nTraces: {out}")
    return 0


def _model_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--effort", default="medium", help="low | medium | high | xhigh | max")


if __name__ == "__main__":
    sys.exit(main())
