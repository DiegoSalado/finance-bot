"""add income_account_id to users

Revision ID: 0002
Revises: 613e4ea718a0
Create Date: 2026-06-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "613e4ea718a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("income_account_id", sa.Integer, sa.ForeignKey("accounts.id")))


def downgrade() -> None:
    op.drop_column("users", "income_account_id")
