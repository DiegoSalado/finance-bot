import logging
from decimal import Decimal

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.database.models import Account, User
from bot.database.session import async_session

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
        )

    @app_commands.command(name="add_account", description="Add a bank account to track")
    @app_commands.describe(
        bank_name="Bank name (e.g. BBVA, Nu)",
        card_type="Card type",
        last_four="Last 4 digits of the card",
        initial_balance="Current balance",
        primary="Set as primary account (receives income deposits)",
    )
    @app_commands.choices(card_type=[
        app_commands.Choice(name="Debit", value="debit"),
        app_commands.Choice(name="Credit", value="credit"),
    ])
    async def add_account(
        self,
        interaction: discord.Interaction,
        bank_name: str,
        card_type: app_commands.Choice[str],
        last_four: str,
        initial_balance: float,
        primary: bool = False,
    ):
        if len(last_four) != 4 or not last_four.isdigit():
            await interaction.response.send_message(
                "Last four must be exactly 4 digits.", ephemeral=True
            )
            return

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.discord_user_id == interaction.user.id)
            )
            user = result.scalar_one_or_none()

            if not user:
                await interaction.response.send_message(
                    "Run `/setup` first to create your profile.", ephemeral=True
                )
                return

            account = Account(
                user_id=user.id,
                bank_name=bank_name,
                card_type=card_type.value,
                last_four=last_four,
                initial_balance=Decimal(str(initial_balance)),
                current_balance=Decimal(str(initial_balance)),
            )
            session.add(account)
            await session.flush()

            if primary:
                user.income_account_id = account.id
                session.add(user)

            await session.commit()

        primary_text = " ⭐ Primary" if primary else ""
        logger.info(f"Account added: {bank_name} *{last_four} for {interaction.user}")
        await interaction.response.send_message(
            f"Account added!{primary_text}\n"
            f"**{bank_name}** {card_type.name} ****{last_four}\n"
            f"**Balance:** ${initial_balance:,.2f}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
