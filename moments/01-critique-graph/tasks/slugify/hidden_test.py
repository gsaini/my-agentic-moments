from solution import slugify


def test_accents_are_removed():
    assert slugify("Crème Brûlée") == "creme-brulee"


def test_punctuation_and_runs_of_separators():
    assert slugify("  many   spaces--and__underscores! ") == "many-spaces-and-underscores"
    assert slugify("C'est l'été") == "c-est-l-ete"


def test_empty_and_symbol_only():
    assert slugify("") == ""
    assert slugify("!!!") == ""


def test_truncates_at_a_word_boundary():
    assert slugify("alpha beta gamma", max_len=10) == "alpha-beta"
    assert slugify("alpha beta gamma", max_len=12) == "alpha-beta"


def test_long_single_word_is_cut():
    assert slugify("supercalifragilistic", max_len=5) == "super"
