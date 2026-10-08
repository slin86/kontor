"""people: depot owners, tax settings per person

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08 03:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("persons") as batch:
        batch.create_index("ix_persons_household_id", ["household_id"])
        batch.create_index("ix_persons_user_id", ["user_id"], unique=True)

    bind = op.get_bind()
    now = datetime.now(UTC)
    users = bind.execute(
        sa.text("SELECT id, household_id, display_name FROM users ORDER BY id")
    ).all()
    owner_of_household: dict[int, int] = {}  # the earliest member owns the existing depot
    for order, (user_id, household_id, name) in enumerate(users):
        bind.execute(
            sa.text(
                "INSERT INTO persons (household_id, name, user_id, sort_order, created_at) "
                "VALUES (:h, :n, :u, :o, :c)"
            ),
            {"h": household_id, "n": name, "u": user_id, "o": order, "c": now},
        )
        person_id = bind.execute(
            sa.text("SELECT id FROM persons WHERE user_id = :u"), {"u": user_id}
        ).scalar_one()
        owner_of_household.setdefault(household_id, person_id)

    with op.batch_alter_table("instruments") as batch:
        batch.add_column(sa.Column("person_id", sa.Integer(), nullable=True))
    for household_id, person_id in owner_of_household.items():
        bind.execute(
            sa.text("UPDATE instruments SET person_id = :p WHERE household_id = :h"),
            {"p": person_id, "h": household_id},
        )
    with op.batch_alter_table("instruments") as batch:
        batch.alter_column("person_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_instruments_person_id", "persons", ["person_id"], ["id"])
        batch.create_index("ix_instruments_person_id", ["person_id"])

    op.create_table(
        "person_tax_settings",
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("church_tax_percent", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("allowance", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("base_interest_percent", sa.Numeric(precision=5, scale=3), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.PrimaryKeyConstraint("person_id"),
    )
    for household_id, person_id in owner_of_household.items():
        bind.execute(
            sa.text(
                "INSERT INTO person_tax_settings "
                "(person_id, church_tax_percent, allowance, base_interest_percent) "
                "SELECT :p, church_tax_percent, allowance, base_interest_percent "
                "FROM tax_settings WHERE household_id = :h"
            ),
            {"p": person_id, "h": household_id},
        )
    op.drop_table("tax_settings")


def downgrade() -> None:
    op.create_table(
        "tax_settings",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("church_tax_percent", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("allowance", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("base_interest_percent", sa.Numeric(precision=5, scale=3), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("household_id"),
    )
    # one row per household: the settings of its first person
    op.execute(
        "INSERT INTO tax_settings "
        "(household_id, church_tax_percent, allowance, base_interest_percent) "
        "SELECT p.household_id, t.church_tax_percent, t.allowance, t.base_interest_percent "
        "FROM person_tax_settings t JOIN persons p ON p.id = t.person_id "
        "WHERE p.id = (SELECT MIN(id) FROM persons WHERE household_id = p.household_id)"
    )
    op.drop_table("person_tax_settings")
    with op.batch_alter_table("instruments") as batch:
        batch.drop_index("ix_instruments_person_id")
        batch.drop_constraint("fk_instruments_person_id", type_="foreignkey")
        batch.drop_column("person_id")
    with op.batch_alter_table("persons") as batch:
        batch.drop_index("ix_persons_user_id")
        batch.drop_index("ix_persons_household_id")
    op.drop_table("persons")
