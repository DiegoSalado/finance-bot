"""add destination_account_id to recurring_expenses

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recurring_expenses", sa.Column("destination_account_id", sa.Integer, sa.ForeignKey("accounts.id")))


def downgrade() -> None:
    op.drop_column("recurring_expenses", "destination_account_id")
