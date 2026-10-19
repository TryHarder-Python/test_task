import json
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TextIO

import httpx
from pydantic import ValidationError

from cache_cli.client import CacheClient, CacheClientError
from cache_cli.settings import STDIO, CliSettings, parse_args

EXIT_OK = 0
EXIT_REQUEST_FAILED = 1
EXIT_USAGE = 2  # same code argparse uses for bad arguments


@contextmanager
def _open_output(target: str, stdout: TextIO) -> Iterator[TextIO]:
    if target == STDIO:
        yield stdout
    else:
        with open(target, "w") as file:
            yield file


def run(
    settings: CliSettings,
    *,
    stdin: TextIO,
    stdout: TextIO,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """Create and read the payload `settings.repeat` times, one JSON line per iteration.

    Per-iteration timings make the effect of the server-side cache visible:
    only the first iteration should pay for the transformer.
    """
    try:
        payload = settings.load_payload(stdin)
    except (OSError, ValidationError) as error:
        print(f"cache-cli: invalid input: {error}", file=sys.stderr)
        return EXIT_USAGE

    try:
        with (
            CacheClient(str(settings.host), transport=transport) as client,
            _open_output(settings.output, stdout) as output,
        ):
            for iteration in range(1, settings.repeat + 1):
                started = time.perf_counter()
                payload_id, created = client.create(payload)
                result = client.fetch(payload_id)
                elapsed_ms = (time.perf_counter() - started) * 1000
                record = {
                    "iteration": iteration,
                    "id": str(payload_id),
                    "status": "created" if created else "existing",
                    "output": result,
                    "elapsed_ms": round(elapsed_ms, 2),
                }
                print(json.dumps(record), file=output, flush=True)
    except CacheClientError as error:
        print(f"cache-cli: {error}", file=sys.stderr)
        return EXIT_REQUEST_FAILED
    except OSError as error:
        print(f"cache-cli: cannot write output: {error}", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


def _format_validation_error(error: ValidationError) -> str:
    long_names = {
        alias: field
        for field, info in CliSettings.model_fields.items()
        for alias in getattr(info.validation_alias, "choices", [])
    }
    lines = []
    for detail in error.errors():
        location = ".".join(str(part) for part in detail["loc"])
        option = long_names.get(location, location)
        lines.append(f"  {'--' + option if option else 'arguments'}: {detail['msg']}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        settings = parse_args(sys.argv[1:] if argv is None else argv)
    except ValidationError as error:
        print(f"cache-cli: invalid arguments\n{_format_validation_error(error)}", file=sys.stderr)
        return EXIT_USAGE
    return run(settings, stdin=sys.stdin, stdout=sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
