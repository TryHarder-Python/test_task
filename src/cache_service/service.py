import asyncio
from uuid import UUID

from cache_service.payload import input_hash, interleave, render
from cache_service.repositories.unit_of_work import UnitOfWork
from cache_service.schemas import PayloadCreate
from cache_service.transformer import Transformer


class PayloadService:
    """Generates payloads while keeping calls to the transformer to a minimum.

    Concurrency relies on the repositories' "first writer wins" inserts rather
    than locks: racing requests converge on the same rows, at worst making one
    redundant transformer call for a string both see for the first time.
    """

    def __init__(self, uow: UnitOfWork, transformer: Transformer) -> None:
        self._uow = uow
        self._transformer = transformer

    async def create(self, request: PayloadCreate) -> tuple[UUID, bool]:
        """Return the payload identifier and whether this call created it."""
        digest = input_hash(request.list_1, request.list_2)
        if (existing_id := await self._uow.payloads.find_id_by_hash(digest)) is not None:
            return existing_id, False

        transformed = await self._transform_all({*request.list_1, *request.list_2})
        output = render(transformed[value] for value in interleave(request.list_1, request.list_2))

        created_id = await self._uow.payloads.add_if_absent(digest, output)
        await self._uow.commit()

        if created_id is not None:
            return created_id, True
        # A concurrent request stored the same payload first; reuse its identifier.
        concurrent_id = await self._uow.payloads.find_id_by_hash(digest)
        assert concurrent_id is not None, "conflicting payload row must exist"
        return concurrent_id, False

    async def get_output(self, payload_id: UUID) -> str | None:
        return await self._uow.payloads.get_output(payload_id)

    async def _transform_all(self, values: set[str]) -> dict[str, str]:
        """Map each distinct value to its transformed form, consulting the cache first."""
        cached = await self._uow.transform_cache.get_many(values)
        missing = sorted(values - cached.keys())
        if not missing:
            return cached

        # The transformer is an independent external call per string, so fan out.
        outputs = await asyncio.gather(*(self._transformer(value) for value in missing))
        fresh = dict(zip(missing, outputs, strict=True))
        await self._uow.transform_cache.add_many(fresh)
        return cached | fresh
