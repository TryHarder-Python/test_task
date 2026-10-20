from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from cache_service.repositories.payload_repository import (
    PayloadRepository,
    PayloadSqlAlchemyRepository,
)
from cache_service.repositories.transform_cache_repository import (
    TransformCacheSqlAlchemyRepository,
    TransformCacheRepository,
)


class UnitOfWork(ABC):
    """Groups repository writes into one transaction; repositories never commit."""

    payloads: PayloadRepository
    transform_cache: TransformCacheRepository

    @abstractmethod
    async def commit(self) -> None: ...


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Runs the repositories on one session; its lifecycle belongs to the caller."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.payloads = PayloadSqlAlchemyRepository(session)
        self.transform_cache = TransformCacheSqlAlchemyRepository(session)

    async def commit(self) -> None:
        await self._session.commit()
