"""add is_income to purchases

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("purchases", sa.Column("is_income", sa.Boolean, server_default="false"))


def downgrade() -> None:
    op.drop_column("purchases", "is_income")
