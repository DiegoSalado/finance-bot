"""initial_schema

Revision ID: 613e4ea718a0
Revises: 
Create Date: 2026-06-27 00:18:24.191691

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '613e4ea718a0'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("discord_user_id", sa.BigInteger, unique=True, nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("monthly_income", sa.Numeric(12, 2)),
        sa.Column("savings_goal", sa.Numeric(12, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("card_type", sa.String(20), nullable=False),
        sa.Column("last_four", sa.String(4), nullable=False),
        sa.Column("initial_balance", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("current_balance", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("track_monthly_metrics", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("notes", sa.Text),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("icon", sa.String(10)),
        sa.Column("monthly_budget", sa.Numeric(12, 2)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
    )

    op.create_table(
        "purchases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id")),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("original_message", sa.Text),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("purchase_date", sa.Date, nullable=False),
        sa.Column("ai_confidence", sa.Numeric(3, 2)),
        sa.Column("extra_data", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "raw_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("discord_message_id", sa.BigInteger, unique=True, nullable=False),
        sa.Column("channel_id", sa.BigInteger, nullable=False),
        sa.Column("original_content", sa.Text, nullable=False),
        sa.Column("processed", sa.Boolean, server_default="false"),
        sa.Column("processing_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "recurring_expenses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id")),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("billing_day", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("auto_register", sa.Boolean, server_default="false"),
        sa.Column("last_billed_at", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("recurring_expenses")
    op.drop_table("raw_messages")
    op.drop_table("purchases")
    op.drop_table("categories")
    op.drop_table("balance_snapshots")
    op.drop_table("accounts")
    op.drop_table("users")
