from uuid import UUID, uuid4

import pytest

from cache_service.schemas import PayloadCreate
from cache_service.service import PayloadService
from tests.support import CountingTransformer, InMemoryPayloadRepository, InMemoryUnitOfWork

SAMPLE = PayloadCreate(
    list_1=["first string", "second string", "third string"],
    list_2=["other string", "another string", "last string"],
)
SAMPLE_OUTPUT = (
    "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
)


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def service(uow: InMemoryUnitOfWork, transformer: CountingTransformer) -> PayloadService:
    return PayloadService(uow, transformer)


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


async def test_create_generates_and_commits_interleaved_transformed_output(
    service: PayloadService, uow: InMemoryUnitOfWork, transformer: CountingTransformer
) -> None:
    payload_id, created = await service.create(SAMPLE)

    assert created
    assert await service.get_output(payload_id) == SAMPLE_OUTPUT
    assert sorted(transformer.calls) == sorted(SAMPLE.list_1 + SAMPLE.list_2)
    assert uow.commits == 1


async def test_transformer_results_are_cached(
    service: PayloadService, uow: InMemoryUnitOfWork
) -> None:
    await service.create(SAMPLE)

    assert uow.transform_cache.entries["first string"] == "FIRST STRING"
    assert len(uow.transform_cache.entries) == 6


async def test_repeated_request_reuses_identifier_without_any_work(
    service: PayloadService, uow: InMemoryUnitOfWork, transformer: CountingTransformer
) -> None:
    first_id, _ = await service.create(SAMPLE)
    transformer.calls.clear()

    second_id, created = await service.create(SAMPLE)

    assert (second_id, created) == (first_id, False)
    assert transformer.calls == []
    assert uow.commits == 1  # nothing new to persist


async def test_only_strings_missing_from_cache_are_transformed(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    await service.create(SAMPLE)
    transformer.calls.clear()

    payload_id, created = await service.create(
        PayloadCreate(list_1=["first string", "new one"], list_2=["last string", "new two"])
    )

    assert created
    assert sorted(transformer.calls) == ["new one", "new two"]
    assert await service.get_output(payload_id) == "FIRST STRING, LAST STRING, NEW ONE, NEW TWO"


async def test_new_combination_of_cached_strings_needs_no_transformer_call(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    await service.create(SAMPLE)
    transformer.calls.clear()

    _, created = await service.create(
        PayloadCreate(list_1=["last string"], list_2=["first string"])
    )

    assert created
    assert transformer.calls == []


async def test_duplicate_strings_within_a_request_are_transformed_once(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    payload_id, _ = await service.create(PayloadCreate(list_1=["a", "a"], list_2=["a", "b"]))

    assert sorted(transformer.calls) == ["a", "b"]
    assert await service.get_output(payload_id) == "A, A, A, B"


async def test_get_output_of_unknown_payload_is_none(service: PayloadService) -> None:
    assert await service.get_output(uuid4()) is None


class RacingPayloadRepository(InMemoryPayloadRepository):
    """Simulates another request storing the same payload right after our lookup."""

    def __init__(self) -> None:
        super().__init__()
        self.winner_id = uuid4()
        self._raced = False

    async def find_id_by_hash(self, input_hash: str) -> UUID | None:
        if not self._raced:
            self._raced = True
            self.rows[input_hash] = (self.winner_id, "stored by the other request")
            return None
        return await super().find_id_by_hash(input_hash)


async def test_losing_a_concurrent_insert_returns_the_winners_identifier(
    uow: InMemoryUnitOfWork, transformer: CountingTransformer
) -> None:
    racing = RacingPayloadRepository()
    uow.payloads = racing

    payload_id, created = await PayloadService(uow, transformer).create(SAMPLE)

    assert (payload_id, created) == (racing.winner_id, False)
