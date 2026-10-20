"""Pure payload-building rules, kept free of I/O so they are trivially testable."""

import hashlib
import json
from collections.abc import Iterable, Sequence

SEPARATOR = ", "


def interleave(first: Sequence[str], second: Sequence[str]) -> list[str]:
    return [item for pair in zip(first, second, strict=True) for item in pair]


def render(items: Iterable[str]) -> str:
    return SEPARATOR.join(items)


def input_hash(list_1: Sequence[str], list_2: Sequence[str]) -> str:
    """Identify a request by its exact input.

    Hashing a JSON encoding (rather than the rendered output) keeps the lists'
    boundaries, so inputs that merely render to the same text stay distinct.
    """
    canonical = json.dumps([list(list_1), list(list_2)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
