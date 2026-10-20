from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cache_service.db import create_session_factory
from cache_service.repositories.payload_repository import PayloadSqlAlchemyRepository
from cache_service.repositories.transform_cache_repository import (
    TransformCacheSqlAlchemyRepository,
)
from cache_service.repositories.unit_of_work import SqlAlchemyUnitOfWork

HASH = "a" * 64


async def test_payload_added_once_per_hash(session: AsyncSession) -> None:
    payloads = PayloadSqlAlchemyRepository(session)

    payload_id = await payloads.add_if_absent(HASH, "A, B")
    duplicate = await payloads.add_if_absent(HASH, "A, B")

    assert payload_id is not None
    assert duplicate is None
    assert await payloads.find_id_by_hash(HASH) == payload_id
    assert await payloads.get_output(payload_id) == "A, B"


async def test_unknown_payload_lookups_return_none(session: AsyncSession) -> None:
    payloads = PayloadSqlAlchemyRepository(session)

    assert await payloads.find_id_by_hash(HASH) is None
    assert await payloads.get_output(uuid4()) is None


async def test_transform_cache_returns_only_stored_entries(session: AsyncSession) -> None:
    cache = TransformCacheSqlAlchemyRepository(session)
    await cache.add_many({"a": "A", "b": "B"})

    assert await cache.get_many({"a", "b", "missing"}) == {"a": "A", "b": "B"}
    assert await cache.get_many(set()) == {}


async def test_transform_cache_keeps_existing_entries(session: AsyncSession) -> None:
    # Concurrent writers may store the same input; the first result must win, not fail.
    cache = TransformCacheSqlAlchemyRepository(session)
    await cache.add_many({"a": "A"})

    await cache.add_many({"a": "other", "b": "B"})

    assert await cache.get_many({"a", "b"}) == {"a": "A", "b": "B"}


async def test_writes_become_visible_to_others_only_on_commit(clean_engine: AsyncEngine) -> None:
    session_factory = create_session_factory(clean_engine)
    async with session_factory() as writer_session, session_factory() as reader_session:
        uow = SqlAlchemyUnitOfWork(writer_session)
        reader = SqlAlchemyUnitOfWork(reader_session)
        await uow.transform_cache.add_many({"a": "A"})
        await uow.payloads.add_if_absent(HASH, "A")

        assert await reader.transform_cache.get_many({"a"}) == {}
        assert await reader.payloads.find_id_by_hash(HASH) is None

        await uow.commit()

        assert await reader.transform_cache.get_many({"a"}) == {"a": "A"}
        assert await reader.payloads.find_id_by_hash(HASH) is not None
