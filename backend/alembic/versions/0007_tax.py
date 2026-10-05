"""tax

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-05 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("instruments") as batch:
        batch.add_column(
            sa.Column(
                "tax_exempt_percent",
                sa.Numeric(precision=5, scale=2),
                server_default="0",
                nullable=False,
            )
        )
    # Existing ETFs get the Teilfreistellung of equity funds; the user can change it per position.
    op.execute("UPDATE instruments SET tax_exempt_percent = 30 WHERE kind = 'ETF'")
    op.create_table(
        "tax_settings",
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("church_tax_percent", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("allowance", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("base_interest_percent", sa.Numeric(precision=5, scale=3), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("household_id"),
    )


def downgrade() -> None:
    op.drop_table("tax_settings")
    with op.batch_alter_table("instruments") as batch:
        batch.drop_column("tax_exempt_percent")
