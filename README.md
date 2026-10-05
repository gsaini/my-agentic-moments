<div align="center">

# ✨ My Agentic Moments

**A journal of small agentic experiments. Each moment asks one question, builds the smallest thing that can answer it, measures it, and writes down what happened.**

[![CI](https://github.com/gsaini/my-agentic-moments/actions/workflows/ci.yml/badge.svg)](https://github.com/gsaini/my-agentic-moments/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Opus%205.5-D97757?style=for-the-badge&logo=anthropic&logoColor=white)
![Moments](https://img.shields.io/badge/Moments-1-8B5CF6?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-EAB308?style=for-the-badge)

</div>

---

## Moments

| # | Moment | Question | Status |
|---|--------|----------|--------|
| 01 | [Critique an agent with a graph — then critique the critique](moments/01-critique-graph/) | Does critiquing an agent's work make it better, and what kind of critique matters? Self-critique vs. test-grounded vs. probing critique with a gate. | Built and tested offline · live run pending |

## How a moment works

1. **Question** — one sentence, answerable.
2. **Build** — the smallest thing that can answer it, on the shared toolkit.
3. **Measure** — against tasks with graders that are code, not opinions; offline tests prove the mechanics, live runs (opt-in) produce the numbers.
4. **Write it down** — what happened, including what didn't work, in the moment's README.

## The shared toolkit

`src/agentic/` grows as the moments need it:

- [`graph.py`](src/agentic/graph.py) — a ~150-line graph runtime: immutable state, nodes, fixed and conditional edges, cycles with a step limit, wiring checked at compile time, a checkpoint per step with resume, and Mermaid diagrams.
- [`llm.py`](src/agentic/llm.py) — structured calls to Claude through the official `anthropic` SDK (Pydantic in, Pydantic out), and a scripted stand-in for offline tests and demos.

## Quick start

```bash
git clone https://github.com/gsaini/my-agentic-moments.git
cd my-agentic-moments
uv sync
uv run pytest                     # everything offline: no API key, no cost
uv run critique-graph demo        # moment 01's walkthrough
```

Live runs need `ANTHROPIC_API_KEY` (or `ant auth login`) and ask for confirmation before spending — see each moment's README.

## Related

- [awesome-software-engineering](https://github.com/gsaini/awesome-software-engineering) study notes: [Graph Engineering](https://github.com/gsaini/awesome-software-engineering/blob/main/notes/graph-engineering.md) · [Loop Engineering](https://github.com/gsaini/awesome-software-engineering/blob/main/notes/loop-engineering.md) · [Building an Agent Evaluator](https://github.com/gsaini/awesome-software-engineering/blob/main/notes/building-agent-evaluators.md)
- [harness-engineering-getting-started](https://github.com/gsaini/harness-engineering-getting-started) — a small agent harness, built from scratch, with evals for each fix

## License

[MIT](LICENSE). Independent learning experiments, not affiliated with Anthropic.
