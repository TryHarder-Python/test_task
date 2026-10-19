"""Shared PostgreSQL fixtures.

Tests run against a real Postgres because the service relies on
Postgres-specific behaviour (`ON CONFLICT`), which SQLite would not prove.
Set `TEST_DATABASE_URL` to reuse an existing (disposable!) database instead
of starting a container.
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cache_service.db import create_engine, create_session_factory
from tests.support import CountingTransformer, alembic_config


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if Path(item.path).is_relative_to(Path(__file__).parent):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return

    # Ryuk (testcontainers' reaper) bind-mounts the Docker socket, which fails on
    # Docker Desktop for macOS; the context manager below already removes the container.
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def migrated_database_url(database_url: str) -> str:
    # Building the schema through the real migrations keeps them covered by the suite.
    command.upgrade(alembic_config(database_url), "head")
    return database_url


@pytest.fixture(scope="session")
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(migrated_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_engine(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE transform_cache, payload"))
    return engine


@pytest.fixture
async def session(clean_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with create_session_factory(clean_engine)() as session:
        yield session


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()
