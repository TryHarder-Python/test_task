import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from cache_cli.settings import parse_args
from cache_service.schemas import PayloadCreate

PAYLOAD_JSON = '{"list_1": ["a"], "list_2": ["b"]}'
PAYLOAD = PayloadCreate(list_1=["a"], list_2=["b"])


def test_short_flags_are_parsed() -> None:
    settings = parse_args(["-h", "http://api:9000", "-r", "3", "-j", PAYLOAD_JSON, "-o", "out"])

    assert str(settings.host) == "http://api:9000/"
    assert settings.repeat == 3
    assert settings.output == "out"
    assert settings.load_payload(io.StringIO()) == PAYLOAD


def test_long_flags_are_parsed(tmp_path: Path) -> None:
    input_file = tmp_path / "payload.json"
    input_file.write_text(PAYLOAD_JSON)

    settings = parse_args(
        ["--host", "http://api:9000", "--repeat", "2", "--input", str(input_file)]
    )

    assert settings.repeat == 2
    assert settings.load_payload(io.StringIO()) == PAYLOAD


def test_defaults_target_local_server_once_writing_to_stdout() -> None:
    settings = parse_args(["-j", PAYLOAD_JSON])

    assert str(settings.host) == "http://localhost:8000/"
    assert settings.repeat == 1
    assert settings.output == "-"


def test_dash_input_reads_payload_from_stdin() -> None:
    settings = parse_args(["-i", "-"])

    assert settings.load_payload(io.StringIO(PAYLOAD_JSON)) == PAYLOAD


def test_environment_does_not_leak_into_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "http://elsewhere:1")

    assert str(parse_args(["-j", PAYLOAD_JSON]).host) == "http://localhost:8000/"


@pytest.mark.parametrize(
    "argv",
    [
        ["-r", "0", "-j", PAYLOAD_JSON],  # repeat must be positive
        ["-h", "not a url", "-j", PAYLOAD_JSON],
        ["-h", "ftp://api", "-j", PAYLOAD_JSON],  # only HTTP(S) servers
        [],  # no payload source
        ["-i", "-", "-j", PAYLOAD_JSON],  # ambiguous payload source
        ["-i", "/does/not/exist.json"],
        ["-j", "{not json"],
        ["-j", '{"list_1": ["a"], "list_2": []}'],  # violates the service schema
    ],
)
def test_invalid_arguments_are_rejected(argv: list[str]) -> None:
    with pytest.raises(ValidationError):
        parse_args(argv)
