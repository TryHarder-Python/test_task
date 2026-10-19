"""Test doubles and helpers shared by the test suites."""

from pathlib import Path

from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CountingTransformer:
    """Transformer fake that records every call, so tests can assert cache hits."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, value: str) -> str:
        self.calls.append(value)
        return value.upper()


def alembic_config(database_url: str) -> Config:
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config
