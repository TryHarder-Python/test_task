# CLAUDE.md

FastAPI caching microservice + `cache-cli` (a coding assessment; code is reviewed
as production code). Design rationale: `docs/design.md`; user-facing docs: `README.md`.

## Commands

```bash
uv sync                                   # install (Python 3.12, uv-managed)
uv run pytest                             # all tests; integration tests need Docker running
uv run pytest -m "not integration"        # unit tests only, no Docker
uv run ruff check && uv run ruff format --check
docker compose up --build -d --wait       # full stack on :8000 (runs migrations on start)
uv run cache-cli -j '{"list_1":["a"],"list_2":["b"]}' -r 3
uv run alembic revision --autogenerate -m "..."   # after changing models.py
```

## Layout

- `src/cache_service/` — `payload.py` pure rules (interleave/render/hash), `service.py`
  caching rules (no SQL), `repositories/` one module per model
  (`payload_repository.py`, `transform_cache_repository.py`, `unit_of_work.py`), each holding
  the ABC interface + its `SqlAlchemy…` implementation, `api.py` routes + dependencies,
  `main.py` app factory/lifespan,
  `models.py` SQLModel tables, `config.py` env settings.
- `cli/cache_cli/` — separate uv workspace package (`cli/pyproject.toml`), installed only
  via the dev group so it stays out of the service image; shares no code with the service.
  `settings.py` argument model (pydantic-settings), `client.py` httpx client, `main.py`
  runner/entry point.
- `migrations/` — Alembic (async env). The app never calls `create_all`.
- `tests/unit/` (no I/O), `tests/integration/` (PostgreSQL via testcontainers),
  `tests/support.py` shared fakes (`CountingTransformer`, `InMemoryUnitOfWork`).

## Conventions

- Service talks to the DB only through `UnitOfWork`; repositories never commit, the
  service does. New queries go into the ABC (`@abstractmethod`), its `SqlAlchemy…` implementation
  and the in-memory fake in `tests/support.py`. Interfaces are ABCs, not Protocols — no type
  checker runs, so ABCs are what catch a missing method.
- PostgreSQL only; upserts use `sqlalchemy.dialects.postgresql.insert` + `ON CONFLICT`.
- Every model change needs a migration — `test_models_match_migrations` enforces it.
- The transformer is injected (`api.get_transformer`); tests override it and assert call counts.
- TDD: write/adjust the failing test first. Unit tests must not need Docker.
- Comments explain *why*, not *how*. Line length 100, ruff-formatted.
- Small conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `build:`, `chore:`).

## Gotchas

- CLI: `-h` is `--host` (per the brief); help is `--help` only. The CLI ignores
  environment variables on purpose (see `CliSettings.settings_customise_sources`).
- testcontainers' Ryuk is disabled in `tests/integration/conftest.py` because its socket
  mount fails on Docker Desktop for macOS.
- `TEST_DATABASE_URL` points tests at an existing database instead of a container — the
  tests truncate its tables.
