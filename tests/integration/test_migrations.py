from alembic import command

from tests.support import alembic_config


def test_models_match_migrations(migrated_database_url: str) -> None:
    # Fails when a model changes without a corresponding migration.
    command.check(alembic_config(migrated_database_url))
