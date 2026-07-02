from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_income: Mapped[float | None] = mapped_column(Numeric(12, 2))
    savings_goal: Mapped[float | None] = mapped_column(Numeric(12, 2))
    income_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    income_account: Mapped["Account | None"] = relationship(foreign_keys=[income_account_id])
    accounts: Mapped[list["Account"]] = relationship(back_populates="user", foreign_keys="Account.user_id")
    purchases: Mapped[list["Purchase"]] = relationship(back_populates="user")
    recurring_expenses: Mapped[list["RecurringExpense"]] = relationship(back_populates="user")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    card_type: Mapped[str] = mapped_column(String(20), nullable=False)
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    initial_balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    current_balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    track_monthly_metrics: Mapped[bool] = mapped_column(Boolean, server_default="true")
    payment_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_source_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="accounts", foreign_keys=[user_id])
    balance_snapshots: Mapped[list["BalanceSnapshot"]] = relationship(back_populates="account")
    purchases: Mapped[list["Purchase"]] = relationship(back_populates="account")
    recurring_expenses: Mapped[list["RecurringExpense"]] = relationship(back_populates="account", foreign_keys="RecurringExpense.account_id")
    payment_source: Mapped["Account | None"] = relationship(foreign_keys="Account.payment_source_account_id")


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)

    account: Mapped["Account"] = relationship(back_populates="balance_snapshots")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(10))
    monthly_budget: Mapped[float | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="category")
    recurring_expenses: Mapped[list["RecurringExpense"]] = relationship(back_populates="category")


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    original_message: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    is_income: Mapped[bool] = mapped_column(Boolean, server_default="false")
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="purchases")
    account: Mapped["Account | None"] = relationship(back_populates="purchases")
    category: Mapped["Category | None"] = relationship(back_populates="purchases")


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_message_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_content: Mapped[str] = mapped_column(Text, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    processing_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecurringExpense(Base):
    __tablename__ = "recurring_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    billing_day: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    auto_register: Mapped[bool] = mapped_column(Boolean, server_default="false")
    destination_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    last_billed_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="recurring_expenses")
    account: Mapped["Account | None"] = relationship(back_populates="recurring_expenses", foreign_keys=[account_id])
    destination_account: Mapped["Account | None"] = relationship(foreign_keys=[destination_account_id])
    category: Mapped["Category | None"] = relationship(back_populates="recurring_expenses")
