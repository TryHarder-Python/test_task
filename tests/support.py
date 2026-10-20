"""Test doubles and helpers shared by the test suites."""

from collections.abc import Collection, Mapping
from pathlib import Path
from uuid import UUID, uuid4

from alembic.config import Config

from cache_service.repositories.payload_repository import PayloadRepository
from cache_service.repositories.transform_cache_repository import TransformCacheRepository
from cache_service.repositories.unit_of_work import UnitOfWork

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CountingTransformer:
    """Transformer fake that records every call, so tests can assert cache hits."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, value: str) -> str:
        self.calls.append(value)
        return value.upper()


def alembic_config(database_url: str) -> Config:
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


class InMemoryPayloadRepository(PayloadRepository):
    """Dict-backed PayloadRepository; mirrors the "first writer wins" semantics."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[UUID, str]] = {}  # input hash -> (id, output)

    async def find_id_by_hash(self, input_hash: str) -> UUID | None:
        row = self.rows.get(input_hash)
        return row[0] if row else None

    async def get_output(self, payload_id: UUID) -> str | None:
        return next((output for id_, output in self.rows.values() if id_ == payload_id), None)

    async def add_if_absent(self, input_hash: str, output: str) -> UUID | None:
        if input_hash in self.rows:
            return None
        payload_id = uuid4()
        self.rows[input_hash] = (payload_id, output)
        return payload_id


class InMemoryTransformCacheRepository(TransformCacheRepository):
    def __init__(self) -> None:
        self.entries: dict[str, str] = {}

    async def get_many(self, inputs: Collection[str]) -> dict[str, str]:
        return {key: self.entries[key] for key in inputs if key in self.entries}

    async def add_many(self, results: Mapping[str, str]) -> None:
        for key, value in results.items():
            self.entries.setdefault(key, value)


class InMemoryUnitOfWork(UnitOfWork):
    """UnitOfWork fake. Writes apply immediately; transactional visibility is
    covered by the PostgreSQL repository tests instead."""

    def __init__(self) -> None:
        self.payloads = InMemoryPayloadRepository()
        self.transform_cache = InMemoryTransformCacheRepository()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1
