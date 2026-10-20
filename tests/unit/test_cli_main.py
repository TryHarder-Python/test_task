import io
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from cache_cli.main import main, run
from cache_cli.settings import parse_args

PAYLOAD_JSON = '{"list_1": ["a"], "list_2": ["b"]}'


class FakeServer:
    """Mimics the service: the first POST creates the payload, later ones find it."""

    def __init__(self) -> None:
        self.payload_id = uuid4()
        self.posts = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            self.posts += 1
            status = 201 if self.posts == 1 else 200
            return httpx.Response(status, json={"id": str(self.payload_id), "message": "ok"})
        return httpx.Response(200, json={"output": "A, B"})


def test_run_writes_one_json_line_per_iteration() -> None:
    server = FakeServer()
    stdout = io.StringIO()

    exit_code = run(
        parse_args(["-r", "3", "-j", PAYLOAD_JSON]),
        stdin=io.StringIO(),
        stdout=stdout,
        transport=httpx.MockTransport(server),
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert exit_code == 0
    assert [line["iteration"] for line in lines] == [1, 2, 3]
    assert [line["status"] for line in lines] == ["created", "existing", "existing"]
    assert {line["id"] for line in lines} == {str(server.payload_id)}
    assert all(line["output"] == "A, B" and line["elapsed_ms"] >= 0 for line in lines)


def test_run_writes_to_output_file(tmp_path: Path) -> None:
    output = tmp_path / "results.jsonl"

    run(
        parse_args(["-j", PAYLOAD_JSON, "-o", str(output)]),
        stdin=io.StringIO(),
        stdout=io.StringIO(),
        transport=httpx.MockTransport(FakeServer()),
    )

    assert json.loads(output.read_text())["output"] == "A, B"


def test_run_fails_cleanly_when_server_errors(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run(
        parse_args(["-j", PAYLOAD_JSON]),
        stdin=io.StringIO(),
        stdout=io.StringIO(),
        transport=httpx.MockTransport(lambda _: httpx.Response(500, text="boom")),
    )

    assert exit_code == 1
    assert "500" in capsys.readouterr().err


def test_main_reports_invalid_arguments_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["-r", "0", "-j", PAYLOAD_JSON]) == 2

    err = capsys.readouterr().err
    assert "repeat" in err
    assert "Traceback" not in err


def test_main_reports_invalid_stdin_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO('{"list_1": ["a"]}'))

    assert main(["-i", "-"]) == 2
    assert capsys.readouterr().err == "cache-cli: invalid input\n  list_2: Field required\n"


def test_main_reports_malformed_input_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_file = tmp_path / "payload.json"
    input_file.write_text("{oops")

    assert main(["-i", str(input_file)]) == 2

    err = capsys.readouterr().err
    assert err.startswith("cache-cli: invalid input\n  input: Invalid JSON")
    assert "pydantic.dev" not in err


@pytest.mark.parametrize("flag", ["-j", "--json"])
def test_main_names_the_json_option_by_its_flag(
    flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([flag, "{oops"]) == 2

    err = capsys.readouterr().err
    assert "  --json: Invalid JSON" in err
    assert "json_payload" not in err


def test_main_points_at_the_offending_item_inside_the_json_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["-j", '{"list_1": ["ok", "bad\\u0000"], "list_2": ["b", "c"]}']) == 2

    assert "  --json list_1.1: Value error, must not contain NUL" in capsys.readouterr().err


def test_cli_does_not_import_the_service() -> None:
    # cache-cli is installed on its own, without the service package; blocking
    # `cache_service` in a fresh interpreter catches any import that would break that.
    code = "import sys; sys.modules['cache_service'] = None; import cache_cli.main"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
