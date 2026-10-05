"""An eval is only as good as its tasks: references must pass, and hidden tests must catch naive solutions."""

from pathlib import Path

import pytest

from critique_graph.sandbox import run_tests
from critique_graph.tasks import load_tasks

REFERENCE = Path(__file__).parent / "reference"
TASKS = load_tasks()


def test_there_are_four_tasks():
    assert [t.id for t in TASKS] == ["csv-line", "merge-intervals", "roman", "slugify"]


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_reference_passes_everything(task):
    code = (REFERENCE / f"{task.id}.py").read_text()
    assert run_tests(code, task.visible_tests).ok
    assert run_tests(code, task.hidden_tests).ok


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_a_naive_solution_passes_the_visible_tests_but_not_the_hidden_ones(task):
    code = (REFERENCE / f"{task.id}_naive.py").read_text()
    assert run_tests(code, task.visible_tests).ok, "visible tests should not give the answer away"
    assert not run_tests(code, task.hidden_tests).ok, "hidden tests must catch the naive solution"


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_the_spec_names_the_function(task):
    assert f"`{task.function}(" in task.spec
