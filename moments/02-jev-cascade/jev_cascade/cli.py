"""`jev-cascade` — the offline demo, one live request, the experiment, or a replay of recorded answers."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from agentic.llm import DEFAULT_MODEL, PRICES, ClaudeLLM, has_credentials
from jev_cascade import jev
from jev_cascade.dataset import Request, load_requests
from jev_cascade.demo import demo_askers, demo_requests
from jev_cascade.experiment import Outcome, collect, load, replay, report, scoreboard
from jev_cascade.graphs import DEFAULT_THRESHOLD, DESCRIPTIONS, build
from jev_cascade.nodes import ask_claude
from jev_cascade.schema import State

NO_JEV = "No TypeSafe key found. Set TYPESAFE_API_KEY (create one at https://console.typesafe.ai/keys), then try again."
NO_CLAUDE = "No Anthropic credentials found. Set ANTHROPIC_API_KEY (or run `ant auth login`), then try again."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jev-cascade", description="Moment 02: Jev first, Claude only when it must.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("graph", help="print a variant as a Mermaid diagram")
    g.add_argument("variant", choices=list(DESCRIPTIONS))

    sub.add_parser("demo", help="offline walkthrough with scripted answers (no keys, nothing measured)")

    r = sub.add_parser("route", help="route one request live through one variant")
    r.add_argument("text")
    r.add_argument("--variant", default="checked", choices=list(DESCRIPTIONS))
    _run_args(r)

    e = sub.add_parser(
        "experiment", help="ask Jev and Claude about every labeled request once, then score every variant"
    )
    e.add_argument("--requests", help="comma-separated request ids (default: all)")
    e.add_argument("--yes", action="store_true", help="confirm the real API calls")
    _run_args(e)

    p = sub.add_parser("replay", help="re-score recorded answers, e.g. at another threshold — no new calls")
    p.add_argument("answers", type=Path, help="an answers.jsonl written by `experiment`")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)

    args = parser.parse_args(argv)
    if args.cmd == "graph":
        print(build(args.variant, *demo_askers()[:2]).mermaid())
        return 0
    if args.cmd == "demo":
        return _demo()
    if args.cmd == "replay":
        print(report(load(args.answers, load_requests()), args.threshold))
        return 0

    # A single-model variant needs only that model's credentials.
    needs = {args.variant} if args.cmd == "route" and args.variant in ("jev", "claude") else {"jev", "claude"}
    if "jev" in needs and not jev.has_key():
        print(NO_JEV)
        return 2
    if "claude" in needs and not has_credentials():
        print(NO_CLAUDE)
        return 2
    ask_jev = jev.asker(jev.live_client(), args.jev_model) if "jev" in needs else None
    claude = ask_claude(ClaudeLLM(args.model, effort=args.effort)) if "claude" in needs else None

    if args.cmd == "route":
        state, _ = build(args.variant, ask_jev, claude, args.threshold).run(State(request=Request("cli", args.text)))
        print(_describe(state))
        return 0

    requests = load_requests(args.requests.split(",") if args.requests else None)
    if not args.yes:
        print(_estimate(len(requests), args))
        return 2
    out = Path("runs") / time.strftime("%Y%m%d-%H%M%S")
    records = collect(requests, ask_jev, claude, out=out / "answers.jsonl")
    text = report(records, args.threshold)
    (out / "scoreboard.md").write_text(f"Claude effort `{args.effort}`\n\n{text}\n", encoding="utf-8")
    print(f"{text}\n\nAnswers: {out / 'answers.jsonl'} — re-score at any threshold with "
          f"`jev-cascade replay {out / 'answers.jsonl'} --threshold 0.8`")  # fmt: skip
    return 0


def _demo() -> int:
    requests = demo_requests()
    records = collect(requests, *demo_askers(requests)[:2])
    results = {variant: replay(records, variant) for variant in DESCRIPTIONS}
    print("Offline demo — scripted answers, to show the mechanics. Nothing here is a measurement.\n")
    for i, record in enumerate(records):
        j = record.jev
        assert j is not None
        print(f"{record.request.id} · {record.request.text!r} (needs {record.request.route})")
        print(f"  Jev says {j.route} (confidence {j.confidence:.2f}); reordered: {j.reordered}; "
              f"Nouls: {' · '.join(f'{k} {p:.2f}' for k, p in j.checks.items())}")  # fmt: skip
        for variant in ("cascade", "checked"):
            print(f"  {variant:8} → {_verdict(results[variant][i])}")
        print()
    print(scoreboard(results))
    return 0


def _verdict(o: Outcome) -> str:
    mark = "✓" if o.correct else "✗"
    if o.answered_by == "jev":
        return f"Jev's {o.route} stands {mark}"
    return f"Claude: {o.route} {mark}  ({'; '.join(o.escalate)})"


def _describe(state: State) -> str:
    lines = [f"→ {state.route}, answered by {'Claude' if state.answered_by == 'claude' else 'Jev'}"]
    if state.escalate:
        lines.append(f"  escalated because: {'; '.join(state.escalate)}")
    if j := state.jev:
        nouls = " · ".join(f"{k} {p:.2f}" for k, p in j.checks.items())
        lines.append(f"  Jev ({j.model}, {j.latency_ms:,.0f} ms): {j.route}, confidence {j.confidence:.2f}; "
                     f"reordered: {j.reordered}; Nouls: {nouls}")  # fmt: skip
    if c := state.claude:
        lines.append(f"  Claude ({c.model}, {c.latency_ms:,.0f} ms): {c.answer.route} — {c.answer.reason}")
    return "\n".join(lines)


def _estimate(n: int, args: argparse.Namespace) -> str:
    claude = "an unknown amount"
    if args.model in PRICES:
        p_in, p_out = PRICES[args.model]
        claude = f"roughly ${n * (700 * p_in + 500 * p_out) / 1e6:.2f}"  # a guess: ~700 tokens in, ~500 out per call
    return (
        f"This asks {args.jev_model} and {args.model} (effort {args.effort}) about {n} requests: {n} Jev requests "
        f'(well under a cent) and {n} Claude calls ({claude}). Try one first (`jev-cascade route "..."`), '
        "then add --yes."
    )


def _run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="the gate's confidence floor")
    p.add_argument("--jev-model", default=jev.JEV_MODEL, help="a versioned Jev model, e.g. jev-1.14.0")
    p.add_argument("--model", default=DEFAULT_MODEL, help="the Claude model")
    p.add_argument("--effort", default="low", help="low | medium | high | xhigh | max (routing is classification)")


if __name__ == "__main__":
    sys.exit(main())
