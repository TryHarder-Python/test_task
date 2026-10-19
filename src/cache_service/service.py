import asyncio
from collections.abc import Iterable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from cache_service.models import Payload, TransformCache
from cache_service.payload import input_hash, interleave, render
from cache_service.schemas import PayloadCreate
from cache_service.transformer import Transformer


class PayloadService:
    """Generates payloads while keeping calls to the transformer to a minimum.

    Concurrent requests are handled with `ON CONFLICT DO NOTHING` rather than
    locks: racing writers converge on the same rows, at worst one redundant
    transformer call is made for a string that two requests see for the first
    time simultaneously.
    """

    def __init__(self, session: AsyncSession, transformer: Transformer) -> None:
        self._session = session
        self._transformer = transformer

    async def create(self, request: PayloadCreate) -> tuple[UUID, bool]:
        """Return the payload identifier and whether this call created it."""
        digest = input_hash(request.list_1, request.list_2)
        if (existing_id := await self._find_id(digest)) is not None:
            return existing_id, False

        transformed = await self._transform_all({*request.list_1, *request.list_2})
        output = render(transformed[value] for value in interleave(request.list_1, request.list_2))

        statement = (
            insert(Payload)
            .values(id=uuid4(), input_hash=digest, output=output)
            .on_conflict_do_nothing(index_elements=[Payload.input_hash])
            .returning(Payload.id)
        )
        created_id = (await self._session.execute(statement)).scalar_one_or_none()
        await self._session.commit()

        if created_id is not None:
            return created_id, True
        # A concurrent request stored the same payload first; reuse its identifier.
        concurrent_id = await self._find_id(digest)
        assert concurrent_id is not None, "conflicting payload row must exist"
        return concurrent_id, False

    async def get_output(self, payload_id: UUID) -> str | None:
        payload = await self._session.get(Payload, payload_id)
        return payload.output if payload else None

    async def _find_id(self, digest: str) -> UUID | None:
        statement = select(Payload.id).where(Payload.input_hash == digest)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def _transform_all(self, values: Iterable[str]) -> dict[str, str]:
        """Map each distinct value to its transformed form, consulting the cache first."""
        values = set(values)
        statement = select(TransformCache.input, TransformCache.output).where(
            TransformCache.input.in_(values)
        )
        results: dict[str, str] = dict((await self._session.execute(statement)).all())

        missing = sorted(values - results.keys())
        if missing:
            # The transformer is an independent external call per string, so fan out.
            outputs = await asyncio.gather(*(self._transformer(value) for value in missing))
            fresh = dict(zip(missing, outputs, strict=True))
            await self._session.execute(
                insert(TransformCache)
                .values([{"input": key, "output": value} for key, value in fresh.items()])
                .on_conflict_do_nothing(index_elements=[TransformCache.input])
            )
            results |= fresh
        return results
