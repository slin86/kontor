"""cashflow items and financings belong to a person; transfers between persons

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("cashflow_items", "financings")


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("person_id", sa.Integer(), nullable=True))
        # existing data belongs to the earliest person of the household, like the depot
        bind.execute(
            sa.text(
                f"UPDATE {table} SET person_id = (SELECT MIN(p.id) FROM persons p "
                f"WHERE p.household_id = {table}.household_id)"
            )
        )
        with op.batch_alter_table(table) as batch:
            batch.alter_column("person_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(f"fk_{table}_person_id", "persons", ["person_id"], ["id"])
            batch.create_index(f"ix_{table}_person_id", ["person_id"])
    with op.batch_alter_table("cashflow_items") as batch:
        batch.add_column(sa.Column("transfer_to_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_cashflow_items_transfer_to_id", "persons", ["transfer_to_id"], ["id"]
        )
        batch.create_index("ix_cashflow_items_transfer_to_id", ["transfer_to_id"])


def downgrade() -> None:
    with op.batch_alter_table("cashflow_items") as batch:
        batch.drop_index("ix_cashflow_items_transfer_to_id")
        batch.drop_constraint("fk_cashflow_items_transfer_to_id", type_="foreignkey")
        batch.drop_column("transfer_to_id")
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_person_id")
            batch.drop_constraint(f"fk_{table}_person_id", type_="foreignkey")
            batch.drop_column("person_id")
