"""Tasks: a spec, visible tests the agent may see, and hidden tests used only for grading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parents[1] / "tasks"


@dataclass(frozen=True)
class Task:
    id: str
    function: str  # the function the agent must write
    spec: str
    visible_tests: str  # shown to the agent and run by the `check` node
    hidden_tests: str  # never shown; used only to grade the final code


def load_tasks(names: list[str] | None = None, root: Path = TASKS_DIR) -> list[Task]:
    tasks = []
    for d in sorted(p for p in root.iterdir() if (p / "task.json").is_file()):
        if names and d.name not in names:
            continue
        meta = json.loads((d / "task.json").read_text(encoding="utf-8"))
        tasks.append(
            Task(
                id=d.name,
                function=meta["function"],
                spec=(d / "spec.md").read_text(encoding="utf-8"),
                visible_tests=(d / "visible_test.py").read_text(encoding="utf-8"),
                hidden_tests=(d / "hidden_test.py").read_text(encoding="utf-8"),
            )
        )
    return tasks
