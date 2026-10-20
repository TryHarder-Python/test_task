from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from cache_service.models import TransformCache


class TransformCacheRepository(ABC):
    """Cache of transformer results, one entry per distinct input string."""

    @abstractmethod
    async def get_many(self, inputs: Collection[str]) -> dict[str, str]:
        """Return cached results for those inputs that have one."""

    @abstractmethod
    async def add_many(self, results: Mapping[str, str]) -> None:
        """Cache results; entries that already exist are kept unchanged."""


class TransformCacheSqlAlchemyRepository(TransformCacheRepository):
    """PostgreSQL dialect: `ON CONFLICT DO NOTHING` lets racing requests converge."""

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
