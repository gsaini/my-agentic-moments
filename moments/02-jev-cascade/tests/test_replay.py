"""Collect once, replay everything: the scores must come from the recorded answers alone."""

from dataclasses import replace

import pytest
from typesafe_sdk import TypeSafeAPITimeoutError

from agentic.llm import LLMError, Usage
from jev_cascade.dataset import Request
from jev_cascade.demo import demo_askers, demo_requests
from jev_cascade.experiment import Record, collect, load, replay, report, summarize, total_cost
from jev_cascade.schema import ClaudeCall, Judgment, RouteAnswer

REQUESTS = demo_requests()


@pytest.fixture(scope="module")
def records():
    return collect(REQUESTS, *demo_askers(REQUESTS)[:2])


def test_answers_survive_a_round_trip(records, tmp_path):
    path = tmp_path / "answers.jsonl"
    written = collect(REQUESTS, *demo_askers(REQUESTS)[:2], out=path)
    assert len(path.read_text().splitlines()) == len(REQUESTS)  # one line per request, written as it arrives
    assert load(path, REQUESTS) == written


def test_a_corrected_label_needs_no_new_calls(records, tmp_path):
    path = tmp_path / "answers.jsonl"
    collect(REQUESTS, *demo_askers(REQUESTS)[:2], out=path)
    relabeled = [replace(r, route="none") if r.id == "n06" else r for r in REQUESTS]
    assert summarize(replay(load(path, relabeled), "jev"))["correct"] == 2  # Jev's "none" now counts as right


def test_changed_text_refuses_old_answers(tmp_path):
    path = tmp_path / "answers.jsonl"
    collect(REQUESTS, *demo_askers(REQUESTS)[:2], out=path)
    edited = [replace(r, text=r.text + "!") if r.id == "p05" else r for r in REQUESTS]
    with pytest.raises(ValueError, match="p05: the request changed"):
        load(path, edited)


def test_threshold_extremes(records):
    jev_only = [o.route for o in replay(records, "jev")]
    assert [o.route for o in replay(records, "cascade", 0.0)] == jev_only  # nothing escalates
    everything = replay(records, "cascade", 1.01)  # confidence never exceeds 1, so everything escalates
    assert [o.route for o in everything] == [o.route for o in replay(records, "claude")]
    assert summarize(everything)["claude_calls"] == len(REQUESTS)


def test_a_cascade_pays_jev_for_everything_and_claude_only_when_it_escalates():
    j = Judgment(
        "ops", {"ops": 1.0}, 0.3, "ops", {"code": 0, "explain": 0, "ops": 1, "data": 0}, "jev-1.13.0", 1000, 90.0
    )
    c = ClaudeCall(RouteAnswer(route="ops", reason="r"), Usage(1, 1_000, 500), "claude-opus-5-5", 2000.0)
    records = [Record(Request("a", "a", "ops"), j, c)]
    claude_only = total_cost(replay(records, "claude"))
    assert claude_only == pytest.approx((1_000 * 4 + 500 * 20) / 1e6)
    assert total_cost(replay(records, "cascade")) == pytest.approx(claude_only + 1000 * 42e-9)  # it escalated
    assert total_cost(replay(records, "cascade", 0.0)) == pytest.approx(1000 * 42e-9)  # it didn't


def test_scripted_models_have_no_price(records):
    assert total_cost(replay(records, "claude")) is None and total_cost(replay(records, "jev")) is None


def test_a_failed_call_is_recorded_and_only_hurts_the_variants_that_need_it():
    def flaky_jev(request):
        if request.id == "p05":
            raise TypeSafeAPITimeoutError("timed out")
        return ask_jev(request)

    def refusing_claude(request):
        raise LLMError("route: the model declined")

    ask_jev, _, _ = demo_askers(REQUESTS)
    records = collect(REQUESTS, flaky_jev, refusing_claude)
    assert (
        "Jev: TypeSafeAPITimeoutError" in records[0].error and "Claude: route: the model declined" in records[0].error
    )
    jev = summarize(replay(records, "jev"))
    assert (jev["errors"], jev["correct"]) == (1, 0)  # p05 lost; the other three were wrong anyway
    assert summarize(replay(records, "claude"))["errors"] == len(REQUESTS)


def test_the_report_has_every_section(records):
    text = report(records)
    for heading in ("**correct**", "Why the gate doubted Jev", "Threshold sweep", "Correct, by trap"):
        assert heading in text
    assert "| none: the wrong answer stands | 1 |" in text  # the double negative
