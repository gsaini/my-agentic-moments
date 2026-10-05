from solution import merge_intervals


def test_empty():
    assert merge_intervals([]) == []


def test_unsorted_input():
    assert merge_intervals([(8, 10), (1, 3), (2, 6)]) == [(1, 6), (8, 10)]


def test_touching_intervals_merge():
    assert merge_intervals([(1, 2), (2, 3)]) == [(1, 3)]


def test_contained_interval():
    assert merge_intervals([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]


def test_single_point_intervals():
    assert merge_intervals([(5, 5), (5, 5), (1, 1)]) == [(1, 1), (5, 5)]


def test_input_is_not_modified():
    data = [(3, 4), (1, 2)]
    merge_intervals(data)
    assert data == [(3, 4), (1, 2)]
