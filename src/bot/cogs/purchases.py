import logging
from datetime import date
from decimal import Decimal

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database.models import Account, Category, Purchase, RecurringExpense, User
from bot.database.session import async_session

logger = logging.getLogger(__name__)


async def _get_user(discord_user_id: int) -> User | None:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.discord_user_id == discord_user_id)
        )
        return result.scalar_one_or_none()


async def account_autocomplete(interaction: discord.Interaction, current: str):
    async with async_session() as session:
        result = await session.execute(
            select(Account)
            .join(User, Account.user_id == User.id)
            .where(User.discord_user_id == interaction.user.id)
        )
        accounts = result.scalars().all()
    return [
        app_commands.Choice(
            name=f"{a.bank_name} {a.card_type} ****{a.last_four}",
            value=a.id,
        )
        for a in accounts
        if current.lower() in f"{a.bank_name} {a.last_four}".lower()
    ][:25]


async def category_autocomplete(interaction: discord.Interaction, current: str):
    async with async_session() as session:
        result = await session.execute(
            select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
        )
        categories = result.scalars().all()
    return [
        app_commands.Choice(name=f"{c.icon} {c.name}", value=c.id)
        for c in categories
        if current.lower() in c.name.lower()
    ][:25]


async def recurring_autocomplete(interaction: discord.Interaction, current: str):
    async with async_session() as session:
        result = await session.execute(
            select(RecurringExpense)
            .join(User, RecurringExpense.user_id == User.id)
            .where(User.discord_user_id == interaction.user.id)
            .where(RecurringExpense.is_active.is_(True))
        )
        expenses = result.scalars().all()
    return [
        app_commands.Choice(
            name=f"{e.title} — ${e.amount:,.2f}",
            value=e.id,
        )
        for e in expenses
        if current.lower() in e.title.lower()
    ][:25]


class PurchasesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="buy", description="Register a purchase")
    @app_commands.describe(
        title="What did you buy?",
        amount="Amount spent",
        account="Which account/card?",
        category="Purchase category",
    )
    @app_commands.autocomplete(account=account_autocomplete, category=category_autocomplete)
    async def buy(
        self,
        interaction: discord.Interaction,
        title: str,
        amount: float,
        account: int,
        category: int,
    ):
        user = await _get_user(interaction.user.id)
        if not user:
            await interaction.response.send_message(
                "Run `/setup` first.", ephemeral=True
            )
            return

        async with async_session() as session:
            acc = await session.get(Account, account)
            cat = await session.get(Category, category)

            if not acc or acc.user_id != user.id:
                await interaction.response.send_message(
                    "Invalid account. Use `/add_account` first.", ephemeral=True
                )
                return

            purchase = Purchase(
                user_id=user.id,
                account_id=account,
                category_id=category,
                title=title,
                amount=Decimal(str(amount)),
                purchase_date=date.today(),
            )
            acc.current_balance -= Decimal(str(amount))
            session.add(purchase)
            session.add(acc)
            await session.commit()

        cat_display = f"{cat.icon} {cat.name}" if cat else "N/A"
        logger.info(f"Purchase: {title} ${amount} by {interaction.user}")
        await interaction.response.send_message(
            f"**Purchase registered!**\n"
            f"📝 {title}\n"
            f"🔴 ${amount:,.2f}\n"
            f"💰 ${acc.current_balance:,.2f}\n"
            f"🏦 {acc.bank_name} {acc.card_type} ****{acc.last_four}\n"
            f"🏷️ {cat_display}\n"
            f"📅 {date.today().strftime('%d/%m/%Y')}"
        )

    @app_commands.command(name="income", description="Register an income (adds to account balance)")
    @app_commands.describe(
        title="Income source",
        amount="Amount received",
        account="Which account?",
        category="Category",
    )
    @app_commands.autocomplete(account=account_autocomplete, category=category_autocomplete)
    async def income(
        self,
        interaction: discord.Interaction,
        title: str,
        amount: float,
        account: int,
        category: int,
    ):
        user = await _get_user(interaction.user.id)
        if not user:
            await interaction.response.send_message(
                "Run `/setup` first.", ephemeral=True
            )
            return

        async with async_session() as session:
            acc = await session.get(Account, account)
            cat = await session.get(Category, category)

            if not acc or acc.user_id != user.id:
                await interaction.response.send_message(
                    "Invalid account.", ephemeral=True
                )
                return

            purchase = Purchase(
                user_id=user.id,
                account_id=account,
                category_id=category,
                title=title,
                amount=Decimal(str(amount)),
                is_income=True,
                purchase_date=date.today(),
            )
            acc.current_balance += Decimal(str(amount))
            session.add(purchase)
            session.add(acc)
            await session.commit()

        cat_display = f"{cat.icon} {cat.name}" if cat else "N/A"
        logger.info(f"Income: {title} ${amount} by {interaction.user}")
        await interaction.response.send_message(
            f"**Income registered!**\n"
            f"📝 {title}\n"
            f"🟢 +${amount:,.2f}\n"
            f"💰 ${acc.current_balance:,.2f}\n"
            f"🏦 {acc.bank_name} {acc.card_type} ****{acc.last_four}\n"
            f"🏷️ {cat_display}\n"
            f"📅 {date.today().strftime('%d/%m/%Y')}"
        )

    @app_commands.command(name="add_category", description="Add a new spending category")
    @app_commands.describe(
        name="Category name",
        icon="Emoji icon",
        monthly_budget="Optional monthly budget limit",
    )
    async def add_category(
        self,
        interaction: discord.Interaction,
        name: str,
        icon: str,
        monthly_budget: float | None = None,
    ):
        async with async_session() as session:
            existing = await session.execute(
                select(Category).where(Category.name == name)
            )
            if existing.scalar_one_or_none():
                await interaction.response.send_message(
                    f"Category **{name}** already exists.", ephemeral=True
                )
                return

            cat = Category(
                name=name,
                icon=icon,
                monthly_budget=Decimal(str(monthly_budget)) if monthly_budget else None,
            )
            session.add(cat)
            await session.commit()

        logger.info(f"Category added: {icon} {name}")
        budget_text = f"\n💵 Budget: ${monthly_budget:,.2f}" if monthly_budget else ""
        await interaction.response.send_message(
            f"Category added! {icon} **{name}**{budget_text}"
        )

    @app_commands.command(name="recurring", description="Add a recurring expense or transfer")
    @app_commands.describe(
        title="Expense name (e.g. Netflix, Rent, Savings transfer)",
        amount="Monthly amount",
        billing_day="Day of month it gets charged (1-31)",
        account="Source account/card",
        category="Expense category",
        destination="Destination account (for transfers between accounts)",
        auto_register="Automatically register on billing day?",
    )
    @app_commands.autocomplete(account=account_autocomplete, category=category_autocomplete, destination=account_autocomplete)
    async def recurring(
        self,
        interaction: discord.Interaction,
        title: str,
        amount: float,
        billing_day: int,
        account: int,
        category: int,
        destination: int | None = None,
        auto_register: bool = False,
    ):
        if not 1 <= billing_day <= 31:
            await interaction.response.send_message(
                "Billing day must be between 1 and 31.", ephemeral=True
            )
            return

        user = await _get_user(interaction.user.id)
        if not user:
            await interaction.response.send_message(
                "Run `/setup` first.", ephemeral=True
            )
            return

        async with async_session() as session:
            acc = await session.get(Account, account)
            cat = await session.get(Category, category)

            if not acc or acc.user_id != user.id:
                await interaction.response.send_message(
                    "Invalid source account.", ephemeral=True
                )
                return

            dest = None
            if destination:
                dest = await session.get(Account, destination)
                if not dest or dest.user_id != user.id:
                    await interaction.response.send_message(
                        "Invalid destination account.", ephemeral=True
                    )
                    return

            expense = RecurringExpense(
                user_id=user.id,
                account_id=account,
                category_id=category,
                title=title,
                amount=Decimal(str(amount)),
                billing_day=billing_day,
                destination_account_id=destination,
                auto_register=auto_register,
            )
            session.add(expense)
            await session.commit()

        cat_display = f"{cat.icon} {cat.name}" if cat else "N/A"
        auto_text = "✅ Auto-register" if auto_register else "📝 Manual"
        dest_text = f"\n➡️ To: {dest.bank_name} ****{dest.last_four}" if dest else ""
        logger.info(f"Recurring added: {title} ${amount} by {interaction.user}")
        await interaction.response.send_message(
            f"**Recurring {'transfer' if dest else 'expense'} added!**\n"
            f"📝 {title}\n"
            f"💰 ${amount:,.2f}\n"
            f"🏦 {acc.bank_name} {acc.card_type} ****{acc.last_four}{dest_text}\n"
            f"🏷️ {cat_display}\n"
            f"📅 Day {billing_day} of each month\n"
            f"{auto_text}"
        )


    @app_commands.command(name="pay_recurring", description="Pay a recurring expense (pre-filled from saved data)")
    @app_commands.describe(
        expense="Which recurring expense?",
        amount_override="Override amount if it changed this month",
    )
    @app_commands.autocomplete(expense=recurring_autocomplete)
    async def pay_recurring(
        self,
        interaction: discord.Interaction,
        expense: int,
        amount_override: float | None = None,
    ):
        user = await _get_user(interaction.user.id)
        if not user:
            await interaction.response.send_message(
                "Run `/setup` first.", ephemeral=True
            )
            return

        async with async_session() as session:
            rec = await session.get(RecurringExpense, expense)
            if not rec or rec.user_id != user.id:
                await interaction.response.send_message(
                    "Invalid recurring expense.", ephemeral=True
                )
                return

            acc = await session.get(Account, rec.account_id)
            cat = await session.get(Category, rec.category_id)
            dest = await session.get(Account, rec.destination_account_id) if rec.destination_account_id else None

            amount = Decimal(str(amount_override)) if amount_override else rec.amount

            purchase = Purchase(
                user_id=user.id,
                account_id=rec.account_id,
                category_id=rec.category_id,
                title=rec.title,
                amount=amount,
                purchase_date=date.today(),
            )
            acc.current_balance -= amount
            if dest:
                dest.current_balance += amount
                session.add(dest)
            rec.last_billed_at = date.today()
            session.add(purchase)
            session.add(acc)
            await session.commit()

        cat_display = f"{cat.icon} {cat.name}" if cat else "N/A"
        override_text = " (adjusted)" if amount_override else ""
        is_transfer = dest is not None
        logger.info(f"Recurring {'transfer' if is_transfer else 'paid'}: {rec.title} ${amount} by {interaction.user}")

        if is_transfer:
            await interaction.response.send_message(
                f"**Transfer completed!**\n"
                f"📝 {rec.title}\n"
                f"💰 ${amount:,.2f}{override_text}\n"
                f"🏦 {acc.bank_name} ****{acc.last_four} → ${acc.current_balance:,.2f}\n"
                f"➡️ {dest.bank_name} ****{dest.last_four} → ${dest.current_balance:,.2f}\n"
                f"📅 {date.today().strftime('%d/%m/%Y')}"
            )
        else:
            await interaction.response.send_message(
                f"**Recurring expense paid!**\n"
                f"📝 {rec.title}\n"
                f"🔴 ${amount:,.2f}{override_text}\n"
                f"💰 ${acc.current_balance:,.2f}\n"
                f"🏦 {acc.bank_name} {acc.card_type} ****{acc.last_four}\n"
                f"🏷️ {cat_display}\n"
                f"📅 {date.today().strftime('%d/%m/%Y')}"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(PurchasesCog(bot))
