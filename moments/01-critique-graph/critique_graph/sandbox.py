"""Run model-written code against tests and probes, in a separate process with a timeout.

This is not a security sandbox: the code runs on your machine with your
permissions. It isolates crashes, hangs, and imports — use a container for
untrusted workloads.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from critique_graph.schema import CheckResult, Probe, ProbeResult

_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}  # no stale .pyc between rounds


def run_tests(code: str, test_source: str, timeout: int = 30) -> CheckResult:
    with tempfile.TemporaryDirectory(prefix="cg-tests-") as tmp:
        d = Path(tmp)
        (d / "solution.py").write_text(code, encoding="utf-8")
        (d / "test_solution.py").write_text(test_source, encoding="utf-8")
        report = d / "report.xml"
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-o", "addopts=",
               f"--junit-xml={report}", "--tb=short", "test_solution.py"]  # fmt: skip
        try:
            proc = subprocess.run(
                cmd, cwd=d, env={**_ENV, "PYTHONPATH": str(d)}, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return CheckResult(0, _count_tests(test_source), f"Timed out after {timeout}s (infinite loop?).")
        if not report.is_file():  # pytest couldn't even start (e.g. a syntax error in the code)
            return CheckResult(0, _count_tests(test_source), (proc.stdout + proc.stderr)[-3_000:])
        suite = ET.parse(report).getroot()
        suite = suite.find("testsuite") if suite.tag == "testsuites" else suite
        total = int(suite.get("tests", 0))
        bad = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        output = _failures(proc.stdout) if bad else ""
        return CheckResult(total - bad - int(suite.get("skipped", 0)), bad, output)


def _count_tests(source: str) -> int:
    try:
        return sum(
            1 for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
        )
    except SyntaxError:
        return 1


def _failures(stdout: str) -> str:
    start = stdout.find("= FAILURES =")
    text = stdout[start:] if start >= 0 else stdout
    return text[-3_000:]


def validate_probe(probe: Probe, function: str) -> str | None:
    """Why a probe can't be run, or None if it's fine. Probes must be one plain call to the task's function."""
    try:
        tree = ast.parse(probe.call, mode="eval")
    except SyntaxError:
        return "call is not a valid expression"
    if not (isinstance(tree.body, ast.Call) and isinstance(tree.body.func, ast.Name) and tree.body.func.id == function):
        return f"call must be a single call to {function}(...)"
    if probe.expected.startswith("raises "):
        return None if probe.expected[7:].isidentifier() else "expected 'raises <ExceptionName>'"
    try:
        ast.literal_eval(probe.expected)
    except (ValueError, SyntaxError):
        return "expected must be a Python literal or 'raises <ExceptionName>'"
    return None


_RUNNER = """
import ast, json, sys
import solution
probes = json.load(open("probes.json"))
out = []
for p in probes:
    want = p["expected"]
    try:
        got = eval(p["call"], vars(solution).copy())
    except Exception as exc:
        name = type(exc).__name__
        out.append({"actual": f"raises {name}", "passed": want == f"raises {name}"})
        continue
    out.append({"actual": repr(got), "passed": (not want.startswith("raises ")) and got == ast.literal_eval(want)})
print(json.dumps(out))
"""


def run_probes(code: str, probes: list[Probe], function: str, timeout: int = 15) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    runnable: list[Probe] = []
    for probe in probes:
        problem = validate_probe(probe, function)
        if problem:
            results.append(ProbeResult(probe.call, probe.expected, f"not run: {problem}", passed=False, valid=False))
        else:
            runnable.append(probe)
    if not runnable:
        return results
    with tempfile.TemporaryDirectory(prefix="cg-probes-") as tmp:
        d = Path(tmp)
        (d / "solution.py").write_text(code, encoding="utf-8")
        (d / "probes.json").write_text(json.dumps([p.model_dump() for p in runnable]), encoding="utf-8")
        (d / "runner.py").write_text(_RUNNER, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "runner.py"], cwd=d, env={**_ENV, "PYTHONPATH": str(d)},
                                  capture_output=True, text=True, timeout=timeout)  # fmt: skip
            outcomes = json.loads(proc.stdout.strip().splitlines()[-1])
        except (subprocess.TimeoutExpired, json.JSONDecodeError, IndexError):
            why = "timed out" if "proc" not in locals() else (proc.stderr.strip().splitlines() or ["no output"])[-1]
            outcomes = [{"actual": f"could not run: {why}", "passed": False}] * len(runnable)
    for probe, outcome in zip(runnable, outcomes, strict=True):
        results.append(ProbeResult(probe.call, probe.expected, outcome["actual"], outcome["passed"]))
    return results
