import pytest

from agentic.llm import ScriptedLLM
from critique_graph.demo import BUGGY, FIXED, demo_llm
from critique_graph.experiment import run_one, scoreboard
from critique_graph.graphs import DESCRIPTIONS, build
from critique_graph.schema import Critique, Draft, Issue
from critique_graph.tasks import load_tasks

ROMAN = load_tasks(["roman"])[0]


@pytest.mark.parametrize("variant", list(DESCRIPTIONS))
def test_every_variant_compiles(variant):
    assert build(variant, demo_llm()).mermaid().startswith("flowchart LR")


def test_g0_is_one_call():
    llm = ScriptedLLM({"draft": [Draft(approach="a", code=FIXED)]})
    outcome = run_one(ROMAN, "G0", llm)
    assert outcome.solved and outcome.usage.calls == 1 and outcome.stop_reason == "single shot"


def test_g3_catches_what_a_lenient_critic_misses():
    outcome = run_one(ROMAN, "G3", demo_llm())
    first, second = outcome.history
    assert (
        first["verdict"] == "pass" and first["overrode"] and first["probes_failed"] == 3
    )  # its own probes contradict it
    assert first["dropped_vague"] == 1
    assert second["verdict"] == "pass" and not second["overrode"]
    assert outcome.solved and outcome.rounds == 2 and outcome.stop_reason == "critic passed"


def test_g2_trusts_the_same_lenient_critic_and_ships_the_bug():
    lenient = Critique(verdict="pass", issues=[])
    llm = ScriptedLLM({"draft": [Draft(approach="a", code=BUGGY)], "critique": [lenient]})
    outcome = run_one(ROMAN, "G2", llm)
    assert outcome.stop_reason == "critic passed" and not outcome.solved


def test_round_budget_bounds_a_critic_that_never_approves():
    nag = Critique(verdict="revise", issues=[Issue(severity="minor", problem="p", evidence="e", fix="f")])
    llm = ScriptedLLM({
        "draft": [Draft(approach="a", code=FIXED)],
        "critique": [nag] * 3,
        "revise": [Draft(approach="a", code=FIXED)] * 2,
    })  # fmt: skip
    outcome = run_one(ROMAN, "G1", llm, max_rounds=3)
    assert outcome.stop_reason == "round budget" and outcome.rounds == 3 and outcome.usage.calls == 6


def test_what_each_critic_gets_to_see():
    llm = demo_llm()
    run_one(ROMAN, "G3", llm)
    critic_prompts = [p for role, p in llm.prompts if role == "critique"]
    assert all("Visible tests:" in p for p in critic_prompts)  # grounded
    # Last round's probes are re-run against the new code, so the critic sees whether the fix held.
    assert "to_roman(40) → 'XL' (expected 'XL') ✓" in critic_prompts[1]
    assert all("Greedy over a value table" not in p for p in critic_prompts)  # never the author's own reasoning

    self_critic = ScriptedLLM(
        {"draft": [Draft(approach="a", code=FIXED)], "critique": [Critique(verdict="pass", issues=[])]}
    )
    run_one(ROMAN, "G1", self_critic)
    assert "Visible tests:" not in [p for role, p in self_critic.prompts if role == "critique"][0]


def test_failures_become_outcomes_not_crashes():
    outcome = run_one(ROMAN, "G1", ScriptedLLM({"draft": [Draft(approach="a", code=FIXED)]}))  # no critique scripted
    assert outcome.error.startswith("LLMError") and not outcome.solved


def test_scoreboard_lists_every_cell():
    outcomes = [run_one(ROMAN, "G0", ScriptedLLM({"draft": [Draft(approach="a", code=BUGGY)]})),
                run_one(ROMAN, "G3", demo_llm())]  # fmt: skip
    board = scoreboard(outcomes, "scripted")
    assert "| roman | ❌ 1/12 · 1r | ✅ 12/12 · 2r |" in board and "**0/1** | **1/1**" in board
