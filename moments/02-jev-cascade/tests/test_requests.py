"""An eval is only as good as its labels: every request names one route and one trap, and the set is balanced."""

from collections import Counter

from jev_cascade.dataset import TRAPS, load_requests
from jev_cascade.demo import CLAUDE, DEMO, JEV
from jev_cascade.routes import ROUTES

REQUESTS = load_requests()


def test_ids_are_unique_and_say_their_trap():
    ids = [r.id for r in REQUESTS]
    assert len(ids) == len(set(ids)) == 54
    initial = {"plain": "p", "negation": "n", "indirection": "i", "distractor": "d", "injection": "j", "boundary": "b"}
    assert set(initial) == set(TRAPS)
    assert all(r.id[0] == initial[r.trap] for r in REQUESTS)


def test_labels_and_traps_are_known_and_spread():
    assert {r.route for r in REQUESTS} == set(ROUTES)
    assert min(Counter(r.route for r in REQUESTS).values()) >= 6
    traps = Counter(r.trap for r in REQUESTS)
    assert set(traps) == set(TRAPS) and min(traps.values()) >= 8
    # Every trap is tested against more than one route, so a trap can't be "solved" by always guessing one route.
    assert all(len({r.route for r in REQUESTS if r.trap == t}) >= 3 for t in TRAPS)


def test_disputable_labels_say_why():
    assert all(r.note for r in REQUESTS if r.trap == "boundary")


def test_the_demo_uses_real_requests():
    assert set(DEMO) == set(JEV) == set(CLAUDE) <= {r.id for r in REQUESTS}
    assert all(CLAUDE[i].route == next(r.route for r in REQUESTS if r.id == i) for i in DEMO)
