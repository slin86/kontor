"""periodic cashflow items can be spread over the months or booked in the due month

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-08 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # existing items keep their behaviour: every cost is spread over the months
    with op.batch_alter_table("cashflow_items") as batch:
        batch.add_column(
            sa.Column("spread", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("cashflow_items") as batch:
        batch.drop_column("spread")
