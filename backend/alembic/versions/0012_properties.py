"""properties with modernisations; financings and cashflow items can belong to one

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-08 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("usage", sa.String(length=16), nullable=False),
        sa.Column("purchase_month", sa.Date(), nullable=False),
        sa.Column("purchase_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("closing_costs", sa.Numeric(14, 2), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("value_as_of", sa.Date(), nullable=False),
        sa.Column("growth_percent", sa.Numeric(6, 2), nullable=False),
        sa.Column("share_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("properties") as batch:
        batch.create_index("ix_properties_household_id", ["household_id"])
        batch.create_index("ix_properties_person_id", ["person_id"])
    op.create_table(
        "property_works",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("value_gain", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("property_works") as batch:
        batch.create_index("ix_property_works_property_id", ["property_id"])
    for table in ("financings", "cashflow_items"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("property_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                f"fk_{table}_property_id", "properties", ["property_id"], ["id"]
            )
            batch.create_index(f"ix_{table}_property_id", ["property_id"])


def downgrade() -> None:
    for table in ("cashflow_items", "financings"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_property_id")
            batch.drop_constraint(f"fk_{table}_property_id", type_="foreignkey")
            batch.drop_column("property_id")
    op.drop_table("property_works")
    op.drop_table("properties")
