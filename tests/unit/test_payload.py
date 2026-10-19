from cache_service.payload import input_hash, interleave, render

LIST_1 = ["first string", "second string", "third string"]
LIST_2 = ["other string", "another string", "last string"]


def test_interleave_alternates_items_starting_with_first_list() -> None:
    assert interleave(["a", "b"], ["1", "2"]) == ["a", "1", "b", "2"]


def test_render_produces_spec_sample_output() -> None:
    transformed = [s.upper() for s in interleave(LIST_1, LIST_2)]

    assert render(transformed) == (
        "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
    )


def test_input_hash_is_stable_for_equal_input() -> None:
    assert input_hash(LIST_1, LIST_2) == input_hash(list(LIST_1), list(LIST_2))


def test_input_hash_depends_on_list_order() -> None:
    assert input_hash(LIST_1, LIST_2) != input_hash(LIST_2, LIST_1)


def test_input_hash_is_not_fooled_by_separators_inside_strings() -> None:
    # A naive "join then hash" would make these collide.
    assert input_hash(["a, b"], ["c"]) != input_hash(["a"], ["b, c"])
