import logging
from decimal import Decimal

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database.models import Account, User
from bot.database.session import async_session


async def _payment_source_autocomplete(interaction: discord.Interaction, current: str):
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


async def _credit_account_autocomplete(interaction: discord.Interaction, current: str):
    async with async_session() as session:
        result = await session.execute(
            select(Account)
            .join(User, Account.user_id == User.id)
            .where(User.discord_user_id == interaction.user.id)
            .where(Account.card_type == "credit")
        )
        accounts = result.scalars().all()
    return [
        app_commands.Choice(
            name=f"{a.bank_name} ****{a.last_four}",
            value=a.id,
        )
        for a in accounts
        if current.lower() in f"{a.bank_name} {a.last_four}".lower()
    ][:25]


logger = logging.getLogger(__name__)


class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configure your profile: monthly income and savings goal")
    @app_commands.describe(
        monthly_income="Your monthly income",
        savings_goal="Your monthly savings goal",
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        monthly_income: float,
        savings_goal: float,
    ):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.discord_user_id == interaction.user.id)
            )
            user = result.scalar_one_or_none()

            if user:
                user.monthly_income = Decimal(str(monthly_income))
                user.savings_goal = Decimal(str(savings_goal))
                action = "updated"
            else:
                user = User(
                    discord_user_id=interaction.user.id,
                    username=interaction.user.display_name,
                    monthly_income=Decimal(str(monthly_income)),
                    savings_goal=Decimal(str(savings_goal)),
                )
                session.add(user)
                action = "created"

            await session.commit()

        logger.info(f"User {action}: {interaction.user} (ID: {interaction.user.id})")
        await interaction.response.send_message(
            f"Profile {action}!\n"
            f"**Income:** ${monthly_income:,.2f}\n"
            f"**Savings goal:** ${savings_goal:,.2f}",
            ephemeral=True,
            delete_after=60,
        )

    @app_commands.command(name="add_account", description="Add a bank account to track")
    @app_commands.describe(
        bank_name="Bank name (e.g. BBVA, Nu)",
        card_type="Card type",
        last_four="Last 4 digits of the card",
        initial_balance="Current balance",
        primary="Set as primary account (receives income deposits)",
        payment_day="Day of month credit card is billed (credit only)",
        payment_source="Account that pays this credit card bill (credit only)",
    )
    @app_commands.choices(card_type=[
        app_commands.Choice(name="Debit", value="debit"),
        app_commands.Choice(name="Credit", value="credit"),
    ])
    @app_commands.autocomplete(payment_source=_payment_source_autocomplete)
    async def add_account(
        self,
        interaction: discord.Interaction,
        bank_name: str,
        card_type: app_commands.Choice[str],
        last_four: str,
        initial_balance: float,
        primary: bool = False,
        payment_day: int | None = None,
        payment_source: int | None = None,
    ):
        if len(last_four) != 4 or not last_four.isdigit():
            await interaction.response.send_message(
                "Last four must be exactly 4 digits.", ephemeral=True, delete_after=60
            )
            return

        if payment_day is not None and not (1 <= payment_day <= 31):
            await interaction.response.send_message(
                "Payment day must be between 1 and 31.", ephemeral=True, delete_after=60
            )
            return

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.discord_user_id == interaction.user.id)
            )
            user = result.scalar_one_or_none()

            if not user:
                await interaction.response.send_message(
                    "Run `/setup` first to create your profile.", ephemeral=True, delete_after=60
                )
                return

            if payment_source:
                src = await session.get(Account, payment_source)
                if not src or src.user_id != user.id:
                    await interaction.response.send_message(
                        "Invalid payment source account.", ephemeral=True, delete_after=60
                    )
                    return

            account = Account(
                user_id=user.id,
                bank_name=bank_name,
                card_type=card_type.value,
                last_four=last_four,
                initial_balance=Decimal(str(initial_balance)),
                current_balance=Decimal(str(initial_balance)),
                payment_day=payment_day,
                payment_source_account_id=payment_source,
            )
            session.add(account)
            await session.flush()

            if primary:
                user.income_account_id = account.id
                session.add(user)

            await session.commit()

        primary_text = " ⭐ Primary" if primary else ""
        payment_text = ""
        if payment_day and payment_source:
            payment_text = f"\n💳 Billed on day {payment_day} from linked account"
        elif payment_day:
            payment_text = f"\n💳 Billed on day {payment_day}"

        logger.info(f"Account added: {bank_name} *{last_four} for {interaction.user}")
        await interaction.response.send_message(
            f"Account added!{primary_text}\n"
            f"**{bank_name}** {card_type.name} ****{last_four}\n"
            f"**Balance:** ${initial_balance:,.2f}"
            f"{payment_text}",
            ephemeral=True,
            delete_after=60,
        )


    @app_commands.command(name="set_credit_payment", description="Set or update billing day and payment source for a credit card")
    @app_commands.describe(
        account="Credit card to update",
        payment_day="Day of month the card is billed (1–31)",
        payment_source="Account that pays this credit card bill",
    )
    @app_commands.autocomplete(account=_credit_account_autocomplete, payment_source=_payment_source_autocomplete)
    async def set_credit_payment(
        self,
        interaction: discord.Interaction,
        account: int,
        payment_day: int,
        payment_source: int,
    ):
        if not (1 <= payment_day <= 31):
            await interaction.response.send_message(
                "Payment day must be between 1 and 31.", ephemeral=True, delete_after=60
            )
            return

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.discord_user_id == interaction.user.id)
            )
            user = result.scalar_one_or_none()
            if not user:
                await interaction.response.send_message(
                    "Run `/setup` first.", ephemeral=True, delete_after=60
                )
                return

            acc = await session.get(Account, account)
            if not acc or acc.user_id != user.id or acc.card_type != "credit":
                await interaction.response.send_message(
                    "Invalid credit card account.", ephemeral=True, delete_after=60
                )
                return

            src = await session.get(Account, payment_source)
            if not src or src.user_id != user.id:
                await interaction.response.send_message(
                    "Invalid payment source account.", ephemeral=True, delete_after=60
                )
                return

            acc.payment_day = payment_day
            acc.payment_source_account_id = payment_source
            session.add(acc)
            await session.commit()

        logger.info(f"Credit payment updated: {acc.bank_name} ****{acc.last_four} → day {payment_day}")
        await interaction.response.send_message(
            f"Updated! 💳 **{acc.bank_name} ****{acc.last_four}**\n"
            f"📅 Billed on day **{payment_day}** of each month\n"
            f"🏦 Paid from: **{src.bank_name} {src.card_type} ****{src.last_four}**",
            ephemeral=True,
            delete_after=60,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
