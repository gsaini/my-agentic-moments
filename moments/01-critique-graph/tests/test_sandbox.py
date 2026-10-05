from critique_graph.sandbox import run_probes, run_tests, validate_probe
from critique_graph.schema import Probe

TEST = "from solution import f\n\ndef test_one():\n    assert f(1) == 2\n\ndef test_two():\n    assert f(2) == 4\n"


def test_counts_passes_and_failures():
    assert run_tests("def f(x):\n    return x * 2\n", TEST).ok
    half = run_tests("def f(x):\n    return 2\n", TEST)
    assert (half.passed, half.failed) == (1, 1) and "assert 2 == 4" in half.output


def test_broken_code_and_hangs_fail_instead_of_crashing():
    syntax = run_tests("def f(x) return x", TEST)
    assert syntax.passed == 0 and syntax.failed >= 1
    hang = run_tests("def f(x):\n    while True:\n        pass\n", TEST, timeout=3)
    assert hang.failed == 2 and "Timed out" in hang.output


def test_probes_report_values_and_exceptions():
    code = "def f(x):\n    if x < 0:\n        raise ValueError\n    return x * 2\n"
    results = run_probes(code, [
        Probe(call="f(2)", expected="4"),
        Probe(call="f(3)", expected="5"),
        Probe(call="f(-1)", expected="raises ValueError"),
        Probe(call="f(-1)", expected="0"),
    ], "f")  # fmt: skip
    assert [(r.actual, r.passed) for r in results] == [
        ("4", True),
        ("6", False),
        ("raises ValueError", True),
        ("raises ValueError", False),
    ]


def test_malformed_probes_are_rejected_not_run():
    assert validate_probe(Probe(call="import os", expected="1"), "f") == "call is not a valid expression"
    assert "single call to f" in validate_probe(Probe(call="g(1)", expected="1"), "f")
    assert "single call to f" in validate_probe(Probe(call="f(1) + 1", expected="1"), "f")
    assert "literal" in validate_probe(Probe(call="f(1)", expected="some value"), "f")
    results = run_probes("def f(x):\n    return x\n", [Probe(call="__import__('os')", expected="1")], "f")
    assert results[0].valid is False and results[0].actual.startswith("not run")


def test_a_hanging_probe_does_not_hang_the_harness():
    results = run_probes(
        "def f(x):\n    while True:\n        pass\n", [Probe(call="f(1)", expected="1")], "f", timeout=3
    )
    assert results[0].passed is False and "timed out" in results[0].actual
