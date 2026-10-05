from solution import parse_csv_line


def test_examples():
    assert parse_csv_line("a,b,c") == ["a", "b", "c"]
    assert parse_csv_line('"a,b",c') == ["a,b", "c"]
