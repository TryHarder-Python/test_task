"""PostgreSQL implementations of the repository ports.

Inserts use `ON CONFLICT DO NOTHING` so concurrent requests writing the same
rows converge instead of failing; this is PostgreSQL-specific SQL.
"""

from collections.abc import Collection, Mapping
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from cache_service.models import Payload, TransformCache


class PostgresPayloadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_id_by_hash(self, input_hash: str) -> UUID | None:
        statement = select(Payload.id).where(Payload.input_hash == input_hash)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_output(self, payload_id: UUID) -> str | None:
        payload = await self._session.get(Payload, payload_id)
        return payload.output if payload else None

    async def add_if_absent(self, input_hash: str, output: str) -> UUID | None:
        statement = (
            insert(Payload)
            .values(id=uuid4(), input_hash=input_hash, output=output)
            .on_conflict_do_nothing(index_elements=[Payload.input_hash])
            .returning(Payload.id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()


class PostgresTransformCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many(self, inputs: Collection[str]) -> dict[str, str]:
        if not inputs:
            return {}
        statement = select(TransformCache.input, TransformCache.output).where(
            TransformCache.input.in_(inputs)
        )
        return dict((await self._session.execute(statement)).all())

    async def add_many(self, results: Mapping[str, str]) -> None:
        if not results:
            return
        await self._session.execute(
            insert(TransformCache)
            .values([{"input": key, "output": value} for key, value in results.items()])
            .on_conflict_do_nothing(index_elements=[TransformCache.input])
        )


class PostgresUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.payloads = PostgresPayloadRepository(session)
        self.transform_cache = PostgresTransformCacheRepository(session)

    async def commit(self) -> None:
        await self._session.commit()
