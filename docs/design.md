# Caching Service — Design

## Goal

A FastAPI microservice that builds "payloads" from two equal-length lists of
strings. Every string is passed through a slow, external-like *transformer*;
the payload is the interleaving of the transformed strings. Transformer
results and generated payloads are cached in PostgreSQL so that repeated work
never reaches the transformer again.

A companion CLI (`cache-cli`) exercises the service programmatically.

## Stack

- Python 3.12, managed with `uv` (`pyproject.toml` + `uv.lock`)
- FastAPI, SQLModel on async SQLAlchemy, `asyncpg`
- PostgreSQL 16 (the only supported database)
- Alembic (async `env.py`) for schema migrations
- `pydantic-settings` for service configuration and CLI parsing
- `httpx` for the CLI client
- `pytest`, `pytest-asyncio`, `testcontainers[postgres]` for tests; `ruff` for lint/format
- Docker (multi-stage, non-root) + `docker-compose` (`db` + `api`)

## Layout

```
src/cache_service/
    config.py       Settings (DATABASE_URL, TRANSFORMER_DELAY_SECONDS)
    db.py           async engine / session factory
    models.py       SQLModel tables
    schemas.py      request / response models
    transformer.py  simulated external transformer
    service.py      caching rules; orchestrates repositories, owns no SQL
    repositories/
        payload_repository.py          PayloadRepository (ABC) + SqlAlchemyPayloadRepository
        transform_cache_repository.py  TransformCacheRepository (ABC) + SqlAlchemy implementation
        unit_of_work.py                UnitOfWork (ABC) + SqlAlchemyUnitOfWork
    api.py          HTTP routes
    main.py         app factory + lifespan
src/cache_cli/
    settings.py     CLI argument model (pydantic-settings)
    client.py       HTTP client wrapper
    main.py         entry point
migrations/         Alembic environment + versions
tests/unit/         pure logic, no I/O
tests/integration/  real Postgres via testcontainers
```

## Data model

| table             | columns                                                              | purpose                        |
|-------------------|----------------------------------------------------------------------|--------------------------------|
| `transform_cache` | `input TEXT PK`, `output TEXT`                                       | transformer result cache       |
| `payload`         | `id UUID PK`, `input_hash CHAR(64) UNIQUE`, `output TEXT`, `created_at` | generated payloads, deduplicated |

`input_hash` is SHA-256 of the canonical JSON of `[list_1, list_2]`; it makes
"same input ⇒ same identifier" a database-enforced invariant. The payload
output is stored so `GET` is a single primary-key lookup.

The schema is owned by Alembic migrations (`migrations/versions/`), with
`SQLModel.metadata` as the autogenerate target. The application never creates
tables itself: the container entrypoint runs `alembic upgrade head` before
starting the server, and integration tests run the same migrations against
their Postgres container, so the migrations themselves are exercised by tests.

## Persistence layers

`PayloadService` depends only on the repository interfaces. Repositories own all
SQL and never commit; the `UnitOfWork` groups a request's writes into one
transaction, and the service decides when to `commit()`. The session itself is
created and closed per request by the API dependency (`get_session` →
`get_unit_of_work` → `get_service`); anything not committed is rolled back on
close. This keeps the caching rules testable with in-memory fakes and the SQL
testable on its own.

Each model has one module holding its interface and its implementation.
Interfaces are ABCs rather than Protocols: the project runs no static type
checker, so an implementation or fake that misses or misspells a method would
go unnoticed with a Protocol, whereas an ABC refuses to instantiate it. The
implementations are named after SQLAlchemy, but use its PostgreSQL dialect
(`ON CONFLICT`), so they require PostgreSQL.

## API

### `POST /payload`

Request: `{"list_1": [str, ...], "list_2": [str, ...]}` — both non-empty and of
equal length, otherwise `422`.

1. Compute `input_hash`; if a payload exists, return its id with `200`.
2. Collect the *unique* strings from both lists, fetch cached results in one
   `SELECT ... WHERE input IN (...)`.
3. Call the transformer only for misses, concurrently (`asyncio.gather`);
   persist with `INSERT ... ON CONFLICT DO NOTHING`.
4. Interleave (`l1[0], l2[0], l1[1], l2[1], ...`), join with `", "`, insert the
   payload with `ON CONFLICT (input_hash) DO NOTHING`, re-read the id.
5. Respond `201` with `{"id": "<uuid>", "message": "Payload created"}`.

### `GET /payload/{id}`

`200` with `{"output": "..."}`, or `404`.

### Known limitation

Two concurrent requests containing the same *previously unseen* string may
both call the transformer for it. Results stay correct (the conflict-safe
insert keeps one row); only one call is wasted. Eliminating it across workers
would need a distributed lock / request coalescing — out of scope.

## Transformer

`async def transform(value: str) -> str`: `value.upper()` after an artificial
`TRANSFORMER_DELAY_SECONDS` sleep (default `0.1`) to simulate an external call.
Provided through a FastAPI dependency so tests can inject a call-counting fake.

## CLI

```
cache-cli [-h|--host URL] [-r|--repeat N] [-i|--input FILE|-] [-j|--json JSON] [-o|--output FILE|-] [--help]
```

- Parsed and validated by `pydantic-settings`: `host` is an HTTP URL, `repeat ≥ 1`,
  exactly one of `--input` / `--json`, the payload validated against the same
  request schema as the service.
- **Deviation from the brief:** the brief assigns `-h` to both `--host` and
  `--help`; `-h` is kept for `--host`, help is `--help` only.
- Each iteration POSTs then GETs and writes one JSON line
  (`iteration`, `id`, `status`, `output`, `elapsed_ms`) to `--output`
  (`-` = stdout). The first iteration is slow, later ones hit the cache.

## Testing

- **Unit:** interleaving, hashing, schema validation, CLI settings parsing,
  CLI client against `httpx.MockTransport`, and the service's caching rules
  against in-memory repository fakes: transformer call counts (no repeated
  calls for cached strings, duplicates within one request transformed once),
  id reuse, commit, and the lost-race path.
- **Integration:** against real Postgres (testcontainers), schema created by
  running the Alembic migrations: repository SQL semantics (first writer wins,
  visibility only after commit), migration drift check, and the HTTP API
  end to end (201/200, 404, 422).
