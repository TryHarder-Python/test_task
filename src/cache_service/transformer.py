import asyncio
from collections.abc import Awaitable, Callable

Transformer = Callable[[str], Awaitable[str]]


def make_transformer(delay_seconds: float) -> Transformer:
    """Build the stand-in for the external transformation service.

    The artificial delay mimics a network round-trip, which is what makes
    caching worthwhile and its effect observable from the CLI.
    """

    async def transform(value: str) -> str:
        await asyncio.sleep(delay_seconds)
        return value.upper()

    return transform
