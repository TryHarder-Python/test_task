import pytest
from pydantic import ValidationError

from cache_service.schemas import PayloadCreate


def test_accepts_lists_of_equal_length() -> None:
    request = PayloadCreate(list_1=["a", "b"], list_2=["c", "d"])

    assert request.list_1 == ["a", "b"]


@pytest.mark.parametrize(
    ("list_1", "list_2"),
    [
        (["a", "b"], ["c"]),  # different lengths
        ([], []),  # nothing to generate
        (["a"], [1]),  # not a string
        (["nul\x00byte"], ["b"]),  # PostgreSQL text cannot store NUL
        (["a"], ["\x00"]),
    ],
)
def test_rejects_invalid_lists(list_1: list, list_2: list) -> None:
    with pytest.raises(ValidationError):
        PayloadCreate(list_1=list_1, list_2=list_2)
