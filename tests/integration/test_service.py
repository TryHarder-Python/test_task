from uuid import uuid4

from alembic import command
from sqlalchemy.ext.asyncio import AsyncSession

from cache_service.schemas import PayloadCreate
from cache_service.service import PayloadService
from tests.support import CountingTransformer, alembic_config

SAMPLE = PayloadCreate(
    list_1=["first string", "second string", "third string"],
    list_2=["other string", "another string", "last string"],
)
SAMPLE_OUTPUT = (
    "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
)


async def test_create_generates_interleaved_transformed_output(
    session: AsyncSession, transformer: CountingTransformer
) -> None:
    service = PayloadService(session, transformer)

    payload_id, created = await service.create(SAMPLE)

    assert created
    assert await service.get_output(payload_id) == SAMPLE_OUTPUT
    assert sorted(transformer.calls) == sorted(SAMPLE.list_1 + SAMPLE.list_2)


async def test_repeated_request_reuses_identifier_without_transforming(
    session: AsyncSession, transformer: CountingTransformer
) -> None:
    service = PayloadService(session, transformer)
    first_id, _ = await service.create(SAMPLE)
    transformer.calls.clear()

    second_id, created = await service.create(SAMPLE)

    assert second_id == first_id
    assert not created
    assert transformer.calls == []


async def test_only_strings_missing_from_cache_are_transformed(
    session: AsyncSession, transformer: CountingTransformer
) -> None:
    service = PayloadService(session, transformer)
    await service.create(SAMPLE)
    transformer.calls.clear()

    payload_id, created = await service.create(
        PayloadCreate(list_1=["first string", "new one"], list_2=["last string", "new two"])
    )

    assert created
    assert sorted(transformer.calls) == ["new one", "new two"]
    assert await service.get_output(payload_id) == "FIRST STRING, LAST STRING, NEW ONE, NEW TWO"


async def test_duplicate_strings_within_a_request_are_transformed_once(
    session: AsyncSession, transformer: CountingTransformer
) -> None:
    service = PayloadService(session, transformer)

    payload_id, _ = await service.create(PayloadCreate(list_1=["a", "a"], list_2=["a", "b"]))

    assert sorted(transformer.calls) == ["a", "b"]
    assert await service.get_output(payload_id) == "A, A, A, B"


async def test_get_output_of_unknown_payload_is_none(
    session: AsyncSession, transformer: CountingTransformer
) -> None:
    assert await PayloadService(session, transformer).get_output(uuid4()) is None


def test_models_match_migrations(migrated_database_url: str) -> None:
    # Fails when a model changes without a corresponding migration.
    command.check(alembic_config(migrated_database_url))
