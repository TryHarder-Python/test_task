from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, model_validator


def _reject_nul(value: str) -> str:
    # PostgreSQL text columns cannot store NUL; rejecting it here turns a database
    # error (HTTP 500) into a clear validation error for the client.
    if "\x00" in value:
        raise ValueError("must not contain NUL characters (\\u0000)")
    return value


StoredStr = Annotated[str, AfterValidator(_reject_nul)]


class PayloadCreate(BaseModel):
    list_1: list[StoredStr] = Field(min_length=1)
    list_2: list[StoredStr] = Field(min_length=1)

    @model_validator(mode="after")
    def _lists_have_same_length(self) -> Self:
        if len(self.list_1) != len(self.list_2):
            raise ValueError("list_1 and list_2 must have the same length")
        return self


class PayloadCreated(BaseModel):
    id: UUID
    message: str


class PayloadRead(BaseModel):
    output: str
