"""Persistence ports the service depends on.

Keeping them as Protocols lets the caching rules be tested against in-memory
fakes, while the PostgreSQL implementations are tested on their own.
"""

from collections.abc import Collection, Mapping
from typing import Protocol
from uuid import UUID


class PayloadRepository(Protocol):
    async def find_id_by_hash(self, input_hash: str) -> UUID | None: ...

    async def get_output(self, payload_id: UUID) -> str | None: ...

    async def add_if_absent(self, input_hash: str, output: str) -> UUID | None:
        """Store a payload; return its id, or None when the hash is already stored."""
        ...


class TransformCacheRepository(Protocol):
    async def get_many(self, inputs: Collection[str]) -> dict[str, str]:
        """Return cached results for those inputs that have one."""
        ...

    async def add_many(self, results: Mapping[str, str]) -> None:
        """Cache results; entries that already exist are kept unchanged."""
        ...


class UnitOfWork(Protocol):
    """Groups repository writes into one transaction; repositories never commit."""

    payloads: PayloadRepository
    transform_cache: TransformCacheRepository

    async def commit(self) -> None: ...
