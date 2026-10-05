"""What flows between the nodes: model outputs (Pydantic) and the graph state (frozen dataclass)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from agentic.llm import Usage
from critique_graph.tasks import Task

# --- What the model returns -------------------------------------------------------


class Draft(BaseModel):
    approach: str = Field(description="One or two sentences on how the code works.")
    code: str = Field(description="The complete Python module: the function plus any helpers and imports.")


class Issue(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    problem: str = Field(description="What is wrong, specifically.")
    evidence: str = Field(
        description="Why you believe it: a failing test, a probe result, or a concrete input and what the code does with it."
    )
    fix: str = Field(description="What to change.")


class Critique(BaseModel):
    verdict: Literal["pass", "revise"] = Field(description="'pass' only if you would ship this code as is.")
    issues: list[Issue] = Field(description="Real defects only. Empty when the verdict is 'pass'.")


class Probe(BaseModel):
    call: str = Field(description="One call to the function, e.g. to_roman(40).")
    expected: str = Field(description="A Python literal (e.g. 'XL', [1, 2], None) or 'raises ValueError'.")


class ProbingCritique(Critique):
    probes: list[Probe] = Field(
        description="Up to 6 calls whose expected results would expose the defects you suspect. They will be run."
    )


# --- What the harness measures ----------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    passed: int
    failed: int
    output: str = ""  # failure details, trimmed

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.passed > 0


@dataclass(frozen=True)
class ProbeResult:
    call: str
    expected: str
    actual: str
    passed: bool
    valid: bool = True  # False when the probe itself was malformed


# --- The graph state --------------------------------------------------------------


@dataclass(frozen=True)
class State:
    task: Task
    code: str = ""
    approach: str = ""
    checks: CheckResult | None = None
    critique: Critique | None = None
    probes: tuple[ProbeResult, ...] = ()  # every probe run so far
    round: int = 0  # drafts written: 1 after the first draft, +1 per revision
    history: tuple[dict, ...] = ()  # one summary per critique, for traces and the scoreboard
    usage: Usage = field(default_factory=Usage)
    stop_reason: str = ""
