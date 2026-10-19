"""Create transform cache and payload tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transform_cache",
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("input", name="pk_transform_cache"),
    )
    op.create_table(
        "payload",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("input_hash", sa.CHAR(64), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payload"),
        sa.UniqueConstraint("input_hash", name="uq_payload_input_hash"),
    )


def downgrade() -> None:
    op.drop_table("payload")
    op.drop_table("transform_cache")
