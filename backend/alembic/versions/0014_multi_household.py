"""an account can belong to several households: persons.user_id is unique per household

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-09 15:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("persons") as batch:
        batch.drop_index("ix_persons_user_id")
        batch.create_index("ix_persons_user_id", ["user_id"])
        batch.create_index("uq_persons_household_user", ["household_id", "user_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("persons") as batch:
        batch.drop_index("uq_persons_household_user")
        batch.drop_index("ix_persons_user_id")
        batch.create_index("ix_persons_user_id", ["user_id"], unique=True)
