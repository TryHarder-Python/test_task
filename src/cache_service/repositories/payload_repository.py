from abc import ABC, abstractmethod
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from cache_service.models import Payload


class PayloadRepository(ABC):
    """Storage of generated payloads, keyed by the hash of their input."""

    @abstractmethod
    async def find_id_by_hash(self, input_hash: str) -> UUID | None: ...

    @abstractmethod
    async def get_output(self, payload_id: UUID) -> str | None: ...

    @abstractmethod
    async def add_if_absent(self, input_hash: str, output: str) -> UUID | None:
        """Store a payload; return its id, or None when the hash is already stored."""


class PayloadSqlAlchemyRepository(PayloadRepository):
    """PostgreSQL dialect: `ON CONFLICT DO NOTHING` lets racing requests converge."""

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
