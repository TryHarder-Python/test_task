import json
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
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
    except OSError as error:
        print(f"cache-cli: cannot read input: {error}", file=sys.stderr)
        return EXIT_USAGE
    except ValidationError as error:
        print(
            f"cache-cli: invalid input\n{_format_errors(error, fallback='input')}", file=sys.stderr
        )
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


def _option_names() -> dict[str, str]:
    """Map field names and aliases to the long flag users actually type."""
    names: dict[str, str] = {}
    for field, info in CliSettings.model_fields.items():
        aliases = [alias for alias in getattr(info.validation_alias, "choices", []) if alias]
        flag = "--" + max(aliases or [field], key=len)
        names |= dict.fromkeys([field, *aliases], flag)
    return names


def _format_errors(
    error: ValidationError, *, fallback: str, names: Mapping[str, str] | None = None
) -> str:
    """Render validation errors as one terse line each, without pydantic's internals."""
    names = names or {}
    lines = []
    for detail in error.errors():
        head, *path = [str(part) for part in detail["loc"]] or [fallback]
        if head in names:
            # Errors inside an option's value (e.g. an item of --json) keep their path.
            label = " ".join([names[head], ".".join(path)]).rstrip()
        else:
            label = ".".join([head, *path])
        lines.append(f"  {label}: {detail['msg']}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        settings = parse_args(sys.argv[1:] if argv is None else argv)
    except ValidationError as error:
        details = _format_errors(error, fallback="arguments", names=_option_names())
        print(f"cache-cli: invalid arguments\n{details}", file=sys.stderr)
        return EXIT_USAGE
    return run(settings, stdin=sys.stdin, stdout=sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
