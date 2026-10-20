# Caching Service

A FastAPI microservice that generates payloads from two lists of strings and
caches the expensive part — the *transformer* — in PostgreSQL, together with a
`cache-cli` tool to exercise it.

A payload is the interleaving of the transformed strings:

```
list_1 = ["first string", "second string"]      ─┐
list_2 = ["other string", "another string"]     ─┤ transform (upper-case, slow)
                                                 ▼
"FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING"
```

The service minimises transformer calls:

- each **distinct** string is transformed at most once — results are stored in
  `transform_cache` and reused across requests;
- an identical request reuses the **same payload identifier** (and makes no
  transformer calls at all).

See [`docs/design.md`](docs/design.md) for the design rationale.

## Quick start

Requirements: Docker, and [uv](https://docs.astral.sh/uv/) for the CLI / local development.

```bash
docker compose up --build -d --wait     # PostgreSQL + API on http://localhost:8000
uv sync                                 # install the CLI and dev tools

uv run cache-cli --json '{"list_1": ["first string", "second string", "third string"],
                          "list_2": ["other string", "another string", "last string"]}' --repeat 3
```

```json
{"iteration": 1, "id": "24fa…", "status": "created",  "output": "FIRST STRING, OTHER STRING, …", "elapsed_ms": 186.53}
{"iteration": 2, "id": "24fa…", "status": "existing", "output": "FIRST STRING, OTHER STRING, …", "elapsed_ms": 7.05}
{"iteration": 3, "id": "24fa…", "status": "existing", "output": "FIRST STRING, OTHER STRING, …", "elapsed_ms": 5.99}
```

Only the first iteration pays for the transformer. Interactive API docs are at
<http://localhost:8000/docs>. Stop with `docker compose down` (`-v` also drops the data).

## API

| Method | Path                  | Success                                                    | Errors                          |
|--------|-----------------------|------------------------------------------------------------|---------------------------------|
| `POST` | `/payload`            | `201 {"id": "<uuid>", "message": "Payload created"}`       | `422` invalid body              |
|        |                       | `200 {"id": "<uuid>", "message": "Payload already exists"}` |                                 |
| `GET`  | `/payload/{id}`       | `200 {"output": "..."}`                                    | `404` unknown id, `422` bad id  |
| `GET`  | `/health`             | `200 {"status": "ok"}`                                     |                                 |

Request body for `POST /payload`: `{"list_1": [...], "list_2": [...]}` — two
non-empty lists of strings of equal length. Strings may not contain NUL
(`\u0000`), which PostgreSQL text cannot store.

## CLI

```
cache-cli [-h|--host URL] [-r|--repeat N] [-i|--input FILE|-] [-j|--json JSON] [-o|--output FILE|-] [--help]
```

| Option         | Default                 | Meaning                                         |
|----------------|-------------------------|-------------------------------------------------|
| `-h, --host`   | `http://localhost:8000` | service base URL (HTTP/HTTPS only)              |
| `-r, --repeat` | `1`                     | number of create + read iterations (≥ 1)        |
| `-i, --input`  |                         | JSON payload file, `-` for stdin                |
| `-j, --json`   |                         | JSON payload given inline                       |
| `-o, --output` | `-`                     | results file (JSON Lines), `-` for stdout       |

Exactly one of `--input` / `--json` is required. Arguments are validated with
pydantic-settings before any request is sent (the payload against the same
schema the service uses). Exit codes: `0` success, `1` request failed,
`2` invalid arguments or input.

> **Deviation from the brief:** the brief assigns `-h` to both `--host` and
> `--help`. `-h` is kept for `--host`; help is available as `--help` only.

```bash
echo '{"list_1": ["a"], "list_2": ["b"]}' | uv run cache-cli -i - -o results.jsonl
```

## Configuration

| Variable                    | Default                                                 |
|-----------------------------|---------------------------------------------------------|
| `DATABASE_URL`              | `postgresql+asyncpg://cache:cache@localhost:5432/cache` |
| `TRANSFORMER_DELAY_SECONDS` | `0.1` — simulated latency of the external transformer   |

## Local development

```bash
uv sync
docker compose up -d --wait db              # PostgreSQL only
uv run alembic upgrade head
uv run uvicorn cache_service.main:app --reload
```

Schema changes go through Alembic:
`uv run alembic revision --autogenerate -m "describe change"`, then review the
generated file. The test suite fails if models and migrations drift apart.

## Tests

```bash
uv run pytest                     # everything (integration tests need Docker)
uv run pytest -m "not integration"
uv run ruff check && uv run ruff format --check
```

- `tests/unit` — pure logic: interleaving, hashing, schemas, CLI parsing,
  CLI client and runner against `httpx.MockTransport`.
- `tests/integration` — service and HTTP API against a real PostgreSQL started
  by testcontainers, with the schema created by the Alembic migrations. A
  call-counting fake transformer verifies the caching guarantees.
  Set `TEST_DATABASE_URL` to use an existing, disposable database instead.

## Design notes and known limitations

- **Concurrency without locks.** Writes use `INSERT … ON CONFLICT DO NOTHING`,
  so concurrent requests converge on the same rows and payload id. Two
  requests that see the same *new* string at the same moment may both call the
  transformer once — a wasted call, not an inconsistency. Removing it across
  workers would need request coalescing or a distributed lock.
- **PostgreSQL only.** The upsert statements are PostgreSQL-specific, which is
  also why tests use a real PostgreSQL rather than SQLite.
- **Stored output.** The rendered payload is stored, so `GET` is a single
  primary-key lookup and never touches the transformer.
- **Transformer failures** propagate as `500`; results of the other strings in
  that request are not cached. Fine for the simulated transformer; a real
  integration would add retries/timeouts.
- **Request size is not limited.** Very large requests (tens of thousands of
  distinct strings) would exceed PostgreSQL's bind-parameter limit; production
  use would cap list sizes or batch the cache queries.
- No authentication, rate limiting, or cache eviction — out of scope.
