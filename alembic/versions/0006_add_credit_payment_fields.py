"""add payment_day and payment_source_account_id to accounts

Revision ID: 0006_add_credit_payment_fields
Revises: 0005_add_is_income_to_purchases
Create Date: 2026-07-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_add_credit_payment_fields"
down_revision = "0005_add_is_income_to_purchases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("payment_day", sa.Integer(), nullable=True))
    op.add_column(
        "accounts",
        sa.Column(
            "payment_source_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "payment_source_account_id")
    op.drop_column("accounts", "payment_day")
