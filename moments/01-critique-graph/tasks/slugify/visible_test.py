from solution import slugify


def test_examples():
    assert slugify("Hello World") == "hello-world"
    assert slugify("Graph Engineering 101") == "graph-engineering-101"
