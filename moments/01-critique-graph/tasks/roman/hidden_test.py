import pytest

from solution import to_roman


@pytest.mark.parametrize("n, expected", [(40, "XL"), (90, "XC"), (400, "CD"), (900, "CM"), (1994, "MCMXCIV"), (3999, "MMMCMXCIX"), (2024, "MMXXIV")])
def test_subtractive_forms(n, expected):
    assert to_roman(n) == expected


@pytest.mark.parametrize("bad", [0, 4000, -1, 3.0, "12"])
def test_rejects_invalid_input(bad):
    with pytest.raises(ValueError):
        to_roman(bad)
