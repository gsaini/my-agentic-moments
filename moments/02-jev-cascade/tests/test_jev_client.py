"""Jev is asked through the real TypeSafe SDK; offline, a scripted transport answers in its wire format."""

import pytest

from jev_cascade.dataset import Request
from jev_cascade.jev import JEV_MODEL, asker, choice_confidence, cost_usd, has_key, scripted_client
from jev_cascade.routes import CHECKS, ROUTES

TEXT = "Roll back the API to v2.3."


def test_confidence_matches_the_documented_formula():
    # docs.typesafe.ai quick start: technical 0.85, billing 0.15, sales 0.0 → confidence 0.78
    assert choice_confidence([0.85, 0.15, 0.0]) == pytest.approx(0.775)
    assert choice_confidence([0.2] * 5) == pytest.approx(0.0)
    assert choice_confidence([1.0, 0.0]) == pytest.approx(1.0)


def test_one_request_carries_all_three_phrasings_to_a_pinned_model():
    seen: list[dict] = []
    script = {"route": {"ops": 0.9, "code": 0.1}, "route_reordered": {"code": 0.6, "ops": 0.4}, "needs_ops": 0.8}
    judgment = asker(scripted_client({TEXT: script}, seen))(Request("x", TEXT))

    [body] = seen  # one request, not one per question
    assert body["model"] == JEV_MODEL == "jev-1.13.0"  # a versioned id, never an alias that can move
    assert body["state"] == {"request": TEXT}  # the request and nothing else
    questions = body["questions"]
    assert set(questions) == {"route", "route_reordered", *(f"needs_{name}" for name in CHECKS)}
    assert list(questions["route"]["criteria"]) == list(ROUTES)
    assert list(questions["route_reordered"]["criteria"]) == list(reversed(ROUTES))
    assert questions["needs_ops"]["criteria"]["true"].startswith("Yes")  # aligned, not inverted

    assert (judgment.route, judgment.reordered) == ("ops", "code")
    assert judgment.confidence == pytest.approx(choice_confidence([0.9, 0.1, 0, 0, 0]))
    assert judgment.checks["ops"] == 0.8 and judgment.checks["data"] == 0.5  # unscripted Noul: "don't know"
    assert judgment.model == "scripted" and judgment.input_tokens > 0


def test_an_unscripted_request_gets_maximally_uncertain_answers():
    judgment = asker(scripted_client({}))(Request("x", "anything"))
    assert judgment.confidence == pytest.approx(0.0)
    assert set(judgment.checks.values()) == {0.5}


def test_key_detection_and_price(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert not has_key()
    monkeypatch.setenv("TYPESAFE_API_KEY", "   ")
    assert not has_key()
    assert cost_usd(1_000_000) == pytest.approx(0.042)  # $42 per billion input tokens
