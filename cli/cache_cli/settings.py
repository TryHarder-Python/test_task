import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Self, TextIO

from pydantic import AliasChoices, Field, HttpUrl, PositiveInt, field_validator, model_validator
from pydantic_settings import BaseSettings, CliSettingsSource, PydanticBaseSettingsSource

from cache_cli.schemas import PayloadCreate

STDIO = "-"


class CliSettings(BaseSettings):
    """Options of `cache-cli`, validated before any request is sent."""

    host: HttpUrl = Field(
        default=HttpUrl("http://localhost:8000"),
        validation_alias=AliasChoices("h", "host"),
        description="base URL of the caching service",
    )
    repeat: PositiveInt = Field(
        default=1,
        validation_alias=AliasChoices("r", "repeat"),
        description="number of create + read iterations",
    )
    input: str | None = Field(
        default=None,
        validation_alias=AliasChoices("i", "input"),
        description="file with the JSON payload, '-' for stdin",
    )
    json_payload: str | None = Field(
        default=None,
        validation_alias=AliasChoices("j", "json"),
        description="the JSON payload itself",
    )
    output: str = Field(
        default=STDIO,
        validation_alias=AliasChoices("o", "output"),
        description="file to write results to, '-' for stdout",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        **_: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Short aliases such as "h" would otherwise also match environment variables
        # (e.g. HOST), letting the shell environment silently change the target server.
        return (init_settings,)

    @field_validator("input")
    @classmethod
    def _input_file_exists(cls, value: str | None) -> str | None:
        if value not in (None, STDIO) and not Path(value).is_file():
            raise ValueError(f"file not found: {value}")
        return value

    @field_validator("json_payload")
    @classmethod
    def _json_matches_schema(cls, value: str | None) -> str | None:
        # Reject a malformed payload up front instead of sending it to the server.
        if value is not None:
            PayloadCreate.model_validate_json(value)
        return value

    @model_validator(mode="after")
    def _exactly_one_payload_source(self) -> Self:
        if (self.input is None) == (self.json_payload is None):
            raise ValueError("provide exactly one of --input or --json")
        return self

    def load_payload(self, stdin: TextIO) -> PayloadCreate:
        if self.json_payload is not None:
            raw = self.json_payload
        elif self.input == STDIO:
            raw = stdin.read()
        else:
            raw = Path(str(self.input)).read_text()
        return PayloadCreate.model_validate_json(raw)


def parse_args(argv: Sequence[str]) -> CliSettings:
    # The brief assigns "-h" to --host, so argparse's built-in "-h/--help" is replaced
    # by a long-only --help.
    parser = argparse.ArgumentParser(
        prog="cache-cli",
        description="Create payloads on the caching service and read them back.",
        add_help=False,
    )
    source = CliSettingsSource(CliSettings, root_parser=parser)
    parser.add_argument("--help", action="help", help="show this help message and exit")
    return CliSettings(_cli_settings_source=source(args=list(argv)))  # type: ignore[call-arg]
