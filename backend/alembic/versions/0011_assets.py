"""assets next to the depot for the net worth

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-08 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("growth_percent", sa.Numeric(6, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("assets") as batch:
        batch.create_index("ix_assets_household_id", ["household_id"])
        batch.create_index("ix_assets_person_id", ["person_id"])


def downgrade() -> None:
    op.drop_table("assets")
