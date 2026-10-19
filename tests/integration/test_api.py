from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from cache_service.api import get_transformer
from cache_service.config import Settings
from cache_service.main import create_app
from tests.support import CountingTransformer

SAMPLE = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}
SAMPLE_OUTPUT = (
    "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
)


@pytest.fixture
async def client(
    migrated_database_url: str, clean_engine: AsyncEngine, transformer: CountingTransformer
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(database_url=migrated_database_url))
    app.dependency_overrides[get_transformer] = lambda: transformer
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


async def test_post_creates_payload_and_get_returns_its_output(client: AsyncClient) -> None:
    created = await client.post("/payload", json=SAMPLE)

    assert created.status_code == 201
    assert created.json()["message"] == "Payload created"

    fetched = await client.get(f"/payload/{created.json()['id']}")

    assert fetched.status_code == 200
    assert fetched.json() == {"output": SAMPLE_OUTPUT}


async def test_repeated_post_returns_existing_identifier(
    client: AsyncClient, transformer: CountingTransformer
) -> None:
    first = await client.post("/payload", json=SAMPLE)
    calls_after_first = len(transformer.calls)

    second = await client.post("/payload", json=SAMPLE)

    assert second.status_code == 200
    assert second.json() == {"id": first.json()["id"], "message": "Payload already exists"}
    assert len(transformer.calls) == calls_after_first


async def test_get_unknown_payload_is_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/payload/{uuid4()}")

    assert response.status_code == 404


async def test_get_with_malformed_identifier_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/payload/not-a-uuid")

    assert response.status_code == 422


async def test_post_with_lists_of_different_length_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/payload", json={"list_1": ["a", "b"], "list_2": ["c"]})

    assert response.status_code == 422
