"""properties: flag that linked financings and items are already the own share

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-09 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("properties") as batch:
        batch.add_column(
            sa.Column("own_share_entered", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("properties") as batch:
        batch.drop_column("own_share_entered")
