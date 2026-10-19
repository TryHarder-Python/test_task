from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CHAR, Column, DateTime, Text, func
from sqlmodel import Field, SQLModel

# Deterministic constraint names keep Alembic autogenerate/check stable across databases.
SQLModel.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class TransformCache(SQLModel, table=True):
    """Result of the (expensive) transformer for a single input string."""

    __tablename__ = "transform_cache"

    input: str = Field(sa_column=Column(Text, primary_key=True))
    output: str = Field(sa_column=Column(Text, nullable=False))


class Payload(SQLModel, table=True):
    """A generated payload; `input_hash` makes identical requests share one identifier."""

    __tablename__ = "payload"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    input_hash: str = Field(sa_column=Column(CHAR(64), nullable=False, unique=True))
    output: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
