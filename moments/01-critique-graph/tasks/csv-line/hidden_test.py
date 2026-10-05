from solution import parse_csv_line


def test_escaped_quotes():
    assert parse_csv_line('"he said ""hi""",x') == ['he said "hi"', "x"]


def test_empty_fields():
    assert parse_csv_line("a,,c") == ["a", "", "c"]


def test_trailing_comma():
    assert parse_csv_line("a,") == ["a", ""]


def test_empty_line():
    assert parse_csv_line("") == [""]


def test_whitespace_is_kept():
    assert parse_csv_line(" a , b ") == [" a ", " b "]


def test_quoted_empty_field():
    assert parse_csv_line('"",x') == ["", "x"]
