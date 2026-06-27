import io
import logging
from calendar import monthrange
from datetime import date, time, timedelta
from decimal import Decimal

import discord
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy import func, or_, select
from zoneinfo import ZoneInfo

from bot.config import DISCORD_CHANNEL_ID
from bot.database.models import (
    Account,
    BalanceSnapshot,
    Category,
    Purchase,
    RecurringExpense,
    User,
)
from bot.database.session import async_session

logger = logging.getLogger(__name__)

MX_TZ = ZoneInfo("America/Mexico_City")
REPORT_TIME = time(hour=22, minute=0, tzinfo=MX_TZ)
FIRST_PAY_DAY = 15
SECOND_PAY_DAY = 30

COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
    "#F8C471", "#82E0AA", "#D7BDE2",
]


class TasksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.daily_job.start()

    def cog_unload(self):
        self.daily_job.cancel()

    @tasks.loop(time=REPORT_TIME)
    async def daily_job(self):
        channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
        if not channel:
            logger.error(f"Channel {DISCORD_CHANNEL_ID} not found")
            return

        logger.info("Running daily job...")

        registered = await self._auto_register_recurring()
        deposited = await self._deposit_income()

        if registered:
            lines = [f"• {r.title} — ${r.amount:,.2f}" for r in registered]
            await channel.send(
                f"🔁 **Auto-registered {len(registered)} recurring expense(s):**\n"
                + "\n".join(lines)
            )

        if deposited:
            for _, amount, acc_name in deposited:
                await channel.send(
                    f"💵 **Income deposited:** ${amount:,.2f} → {acc_name}"
                )

        await self._send_daily_report(channel)

        today = date.today()
        if today.weekday() == 6:
            await self._send_weekly_report(channel)
        if today.day == 1:
            await self._send_monthly_report(channel)

    @daily_job.before_loop
    async def before_daily_job(self):
        await self.bot.wait_until_ready()

    # ── Auto-register recurring expenses ──

    async def _auto_register_recurring(self) -> list:
        today = date.today()
        async with async_session() as session:
            result = await session.execute(
                select(RecurringExpense)
                .where(RecurringExpense.is_active.is_(True))
                .where(RecurringExpense.auto_register.is_(True))
                .where(RecurringExpense.billing_day == today.day)
                .where(
                    or_(
                        RecurringExpense.last_billed_at.is_(None),
                        func.extract("month", RecurringExpense.last_billed_at) != today.month,
                    )
                )
            )
            expenses = result.scalars().all()

            for rec in expenses:
                acc = await session.get(Account, rec.account_id)
                dest = (
                    await session.get(Account, rec.destination_account_id)
                    if rec.destination_account_id
                    else None
                )

                purchase = Purchase(
                    user_id=rec.user_id,
                    account_id=rec.account_id,
                    category_id=rec.category_id,
                    title=rec.title,
                    amount=rec.amount,
                    purchase_date=today,
                )
                acc.current_balance -= rec.amount
                if dest:
                    dest.current_balance += rec.amount
                    session.add(dest)
                rec.last_billed_at = today
                session.add(purchase)
                session.add(acc)

            await session.commit()
            logger.info(f"Auto-registered {len(expenses)} recurring expenses")
        return expenses

    # ── Income deposit on pay days ──

    async def _deposit_income(self) -> list[tuple[str, Decimal, str]]:
        today = date.today()
        _, last_day = monthrange(today.year, today.month)
        pay_day_2 = min(SECOND_PAY_DAY, last_day)

        if today.day not in (FIRST_PAY_DAY, pay_day_2):
            return []

        deposited = []
        async with async_session() as session:
            users = (
                await session.execute(
                    select(User).where(User.income_account_id.isnot(None))
                )
            ).scalars().all()

            for user in users:
                if not user.monthly_income:
                    continue
                acc = await session.get(Account, user.income_account_id)
                if not acc:
                    continue

                existing = (
                    await session.execute(
                        select(BalanceSnapshot)
                        .where(BalanceSnapshot.account_id == acc.id)
                        .where(func.date(BalanceSnapshot.recorded_at) == today)
                        .where(BalanceSnapshot.notes == "income_deposit")
                    )
                ).scalar_one_or_none()
                if existing:
                    continue

                deposit = user.monthly_income / 2
                acc.current_balance += deposit
                session.add(acc)
                session.add(
                    BalanceSnapshot(
                        account_id=acc.id,
                        balance=acc.current_balance,
                        notes="income_deposit",
                    )
                )
                deposited.append((
                    user.username,
                    deposit,
                    f"{acc.bank_name} {acc.card_type}",
                ))

            await session.commit()
        return deposited

    # ── Daily report ──

    @staticmethod
    def _progress_bar(pct: float, length: int = 15) -> str:
        pct = max(0, min(pct, 100))
        filled = round(length * pct / 100)
        empty = length - filled
        if pct <= 50:
            bar_char = "🟩"
        elif pct <= 80:
            bar_char = "🟨"
        else:
            bar_char = "🟥"
        return bar_char * filled + "⬛" * empty

    async def _send_daily_report(self, channel: discord.TextChannel):
        today = date.today()
        first_of_month = today.replace(day=1)
        _, last_day = monthrange(today.year, today.month)
        days_left = last_day - today.day

        async with async_session() as session:
            users = (await session.execute(select(User))).scalars().all()

            for user in users:
                accounts = (
                    await session.execute(
                        select(Account).where(Account.user_id == user.id)
                    )
                ).scalars().all()

                if not accounts:
                    continue

                total_today = Decimal(0)
                total_month = Decimal(0)

                embed = discord.Embed(
                    title=f"📊 Daily Report — {today.strftime('%d/%m/%Y')}",
                    color=0x4ECDC4,
                )

                for acc in accounts:
                    today_sum = (
                        await session.execute(
                            select(func.coalesce(func.sum(Purchase.amount), 0))
                            .where(Purchase.account_id == acc.id)
                            .where(Purchase.purchase_date == today)
                            .where(Purchase.is_income.is_(False))
                        )
                    ).scalar()

                    month_sum = (
                        await session.execute(
                            select(func.coalesce(func.sum(Purchase.amount), 0))
                            .where(Purchase.account_id == acc.id)
                            .where(Purchase.purchase_date >= first_of_month)
                            .where(Purchase.is_income.is_(False))
                        )
                    ).scalar()

                    total_today += today_sum
                    total_month += month_sum

                    is_primary = acc.id == user.income_account_id
                    marker = " ⭐" if is_primary else ""
                    embed.add_field(
                        name=f"💳 {acc.bank_name} {acc.card_type}{marker}",
                        value=(
                            f"Today: **${today_sum:,.2f}**\n"
                            f"Balance: **${acc.current_balance:,.2f}**"
                        ),
                        inline=True,
                    )

                monthly_budget = Decimal(str(user.monthly_income or 0)) - Decimal(str(user.savings_goal or 0))

                if monthly_budget > 0:
                    pct_used = float(total_month / monthly_budget * 100)
                    remaining = monthly_budget - total_month
                    daily_budget = remaining / max(days_left, 1)

                    bar = self._progress_bar(pct_used)

                    if remaining >= 0:
                        status = f"✅ **${remaining:,.2f}** remaining (~${daily_budget:,.2f}/day)"
                    else:
                        status = f"🔴 Over budget by **${abs(remaining):,.2f}**"

                    embed.add_field(
                        name="📈 Monthly Progress",
                        value=(
                            f"{bar} {pct_used:.1f}%\n"
                            f"Budget: ${monthly_budget:,.2f} "
                            f"Spent: **${total_month:,.2f}**\n"
                            f"{status}"
                        ),
                        inline=False,
                    )

                embed.set_footer(text=f"📅 {days_left} days left in the month")
                await channel.send(embed=embed)

    # ── Weekly report with chart ──

    async def _send_weekly_report(self, channel: discord.TextChannel):
        today = date.today()
        week_start = today - timedelta(days=6)

        async with async_session() as session:
            users = (await session.execute(select(User))).scalars().all()

            for user in users:
                cat_spending = (
                    await session.execute(
                        select(
                            Category.name,
                            Category.icon,
                            func.sum(Purchase.amount).label("total"),
                        )
                        .join(Purchase, Purchase.category_id == Category.id)
                        .where(Purchase.user_id == user.id)
                        .where(Purchase.purchase_date >= week_start)
                        .where(Purchase.purchase_date <= today)
                        .where(Purchase.is_income.is_(False))
                        .group_by(Category.id, Category.name, Category.icon)
                        .order_by(func.sum(Purchase.amount).desc())
                    )
                ).all()

                if not cat_spending:
                    await channel.send(
                        f"📊 **Weekly Report — {week_start.strftime('%d/%m')} to "
                        f"{today.strftime('%d/%m/%Y')}**\nNo spending this week! 🎉"
                    )
                    continue

                cat_spending = [r for r in cat_spending if r.total > 0]
                if not cat_spending:
                    await channel.send(
                        f"📊 **Weekly Report — {week_start.strftime('%d/%m')} to "
                        f"{today.strftime('%d/%m/%Y')}**\nNo spending this week! 🎉"
                    )
                    continue

                names = [f"{r.icon} {r.name}" for r in cat_spending]
                amounts = [float(r.total) for r in cat_spending]
                total = sum(amounts)

                fig, ax = plt.subplots(figsize=(8, 6))
                fig.patch.set_facecolor("#2C2F33")
                ax.set_facecolor("#2C2F33")

                wedges, texts, autotexts = ax.pie(
                    amounts,
                    labels=names,
                    autopct="%1.1f%%",
                    colors=COLORS[: len(names)],
                    textprops={"color": "white", "fontsize": 10},
                )
                for t in autotexts:
                    t.set_fontsize(9)
                    t.set_color("white")

                ax.set_title(
                    f"Weekly Spending — ${total:,.2f}\n"
                    f"{week_start.strftime('%d/%m')} to {today.strftime('%d/%m/%Y')}",
                    color="white",
                    fontsize=14,
                    fontweight="bold",
                )

                buf = io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="#2C2F33")
                buf.seek(0)
                plt.close(fig)

                # Non-primary account balances
                query = select(Account).where(Account.user_id == user.id)
                if user.income_account_id:
                    query = query.where(Account.id != user.income_account_id)
                accounts = (await session.execute(query)).scalars().all()

                balance_lines = (
                    "\n".join(
                        f"💳 {a.bank_name} {a.card_type}: **${a.current_balance:,.2f}**"
                        for a in accounts
                    )
                    if accounts
                    else "No secondary accounts"
                )

                await channel.send(
                    f"📊 **Weekly Report**\n\n"
                    f"💰 **Secondary Account Balances:**\n{balance_lines}",
                    file=discord.File(buf, filename="weekly_spending.png"),
                )

    # ── Monthly report with charts ──

    def _make_chart(self, draw_fn, filename: str) -> discord.File:
        fig, ax = plt.subplots(figsize=(9, 6))
        fig.patch.set_facecolor("#2C2F33")
        ax.set_facecolor("#2C2F33")
        draw_fn(fig, ax)
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="#2C2F33")
        buf.seek(0)
        plt.close(fig)
        return discord.File(buf, filename=filename)

    async def _send_monthly_report(self, channel, target_year=None, target_month=None):
        today = date.today()
        if target_year and target_month:
            year, month = target_year, target_month
        elif today.month == 1:
            year, month = today.year - 1, 12
        else:
            year, month = today.year, today.month - 1

        _, last_day = monthrange(year, month)
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)

        async with async_session() as session:
            users = (await session.execute(select(User))).scalars().all()

            for user in users:
                expenses = (
                    await session.execute(
                        select(Purchase)
                        .where(Purchase.user_id == user.id)
                        .where(Purchase.purchase_date >= month_start)
                        .where(Purchase.purchase_date <= month_end)
                        .where(Purchase.is_income.is_(False))
                    )
                ).scalars().all()

                if not expenses:
                    await channel.send(
                        f"📊 **Monthly Report — {month_start.strftime('%B %Y')}**\n"
                        "No spending recorded!"
                    )
                    continue

                total_spent = sum(p.amount for p in expenses)

                # ── Data queries ──

                weekly_totals: dict[int, Decimal] = {}
                for p in expenses:
                    week = (p.purchase_date.day - 1) // 7 + 1
                    weekly_totals[week] = weekly_totals.get(week, Decimal(0)) + p.amount

                cat_spending = (
                    await session.execute(
                        select(
                            Category.name,
                            Category.icon,
                            func.sum(Purchase.amount).label("total"),
                        )
                        .join(Purchase, Purchase.category_id == Category.id)
                        .where(Purchase.user_id == user.id)
                        .where(Purchase.purchase_date >= month_start)
                        .where(Purchase.purchase_date <= month_end)
                        .where(Purchase.is_income.is_(False))
                        .group_by(Category.id, Category.name, Category.icon)
                        .order_by(func.sum(Purchase.amount).desc())
                    )
                ).all()
                cat_spending = [r for r in cat_spending if r.total > 0]

                card_usage = (
                    await session.execute(
                        select(
                            Account.bank_name,
                            Account.card_type,
                            Account.last_four,
                            func.count(Purchase.id).label("count"),
                            func.sum(Purchase.amount).label("total"),
                        )
                        .join(Purchase, Purchase.account_id == Account.id)
                        .where(Purchase.user_id == user.id)
                        .where(Purchase.purchase_date >= month_start)
                        .where(Purchase.purchase_date <= month_end)
                        .where(Purchase.is_income.is_(False))
                        .group_by(Account.id, Account.bank_name, Account.card_type, Account.last_four)
                        .order_by(func.sum(Purchase.amount).desc())
                    )
                ).all()

                # Income deposited this month
                income_deposited = Decimal(0)
                if user.income_account_id:
                    deposits = (
                        await session.execute(
                            select(BalanceSnapshot)
                            .where(BalanceSnapshot.account_id == user.income_account_id)
                            .where(BalanceSnapshot.notes == "income_deposit")
                            .where(func.date(BalanceSnapshot.recorded_at) >= month_start)
                            .where(func.date(BalanceSnapshot.recorded_at) <= month_end)
                        )
                    ).scalars().all()
                    income_deposited = sum(
                        (d.balance for d in deposits), Decimal(0)
                    )
                    # Each snapshot stores the balance AFTER deposit, so count deposits instead
                    income_deposited = Decimal(str(user.monthly_income or 0)) / 2 * len(deposits)

                accounts = (
                    await session.execute(
                        select(Account).where(Account.user_id == user.id)
                    )
                ).scalars().all()

                # ── Chart 1: Weekly timeline ──

                def draw_timeline(fig, ax):
                    weeks = sorted(weekly_totals.keys())
                    values = [float(weekly_totals[w]) for w in weeks]
                    labels = [f"Sem {w}" for w in weeks]

                    ax.plot(labels, values, "o-", color="#4ECDC4", linewidth=2.5, markersize=10)
                    ax.fill_between(labels, values, alpha=0.3, color="#4ECDC4")
                    for i, v in enumerate(values):
                        ax.annotate(
                            f"${v:,.0f}", (labels[i], v),
                            textcoords="offset points", xytext=(0, 14),
                            ha="center", color="white", fontsize=11, fontweight="bold",
                        )
                    ax.set_title(
                        f"Weekly Spending — {month_start.strftime('%B %Y')}",
                        color="white", fontsize=14, fontweight="bold", pad=15,
                    )
                    ax.tick_params(colors="white", labelsize=11)
                    for spine in ("top", "right"):
                        ax.spines[spine].set_visible(False)
                    for spine in ("bottom", "left"):
                        ax.spines[spine].set_color("#555555")

                timeline_file = self._make_chart(draw_timeline, "timeline.png")
                await channel.send(file=timeline_file)

                # ── Chart 2: Category pie ──

                if cat_spending:
                    def draw_pie(fig, ax):
                        names = [f"{r.icon} {r.name}" for r in cat_spending]
                        amounts = [float(r.total) for r in cat_spending]
                        total = sum(amounts)
                        colors = COLORS[: len(names)]

                        wedges, texts, autotexts = ax.pie(
                            amounts,
                            labels=names,
                            autopct=lambda pct: f"${total * pct / 100:,.0f}\n({pct:.1f}%)",
                            colors=colors,
                            textprops={"color": "white", "fontsize": 10},
                            pctdistance=0.75,
                            startangle=90,
                        )
                        for t in autotexts:
                            t.set_fontsize(9)
                            t.set_color("white")
                        ax.set_title(
                            f"Spending by Category — ${total:,.2f}",
                            color="white", fontsize=14, fontweight="bold", pad=15,
                        )

                    pie_file = self._make_chart(draw_pie, "categories.png")
                    await channel.send(file=pie_file)

                # ── Text summary embed ──

                monthly_budget = Decimal(str(user.monthly_income or 0)) - Decimal(str(user.savings_goal or 0))
                saved = Decimal(str(user.monthly_income or 0)) - total_spent
                savings_goal = Decimal(str(user.savings_goal or 0))

                top_cat = cat_spending[0] if cat_spending else None
                top_card = card_usage[0] if card_usage else None

                if saved >= savings_goal and savings_goal > 0:
                    savings_text = f"✅ Saved **${saved:,.2f}** — goal of ${savings_goal:,.2f} reached!"
                elif saved > 0:
                    savings_text = f"⚠️ Saved **${saved:,.2f}** — below goal of ${savings_goal:,.2f}"
                else:
                    savings_text = f"🔴 Overspent by **${abs(saved):,.2f}**"

                embed = discord.Embed(
                    title=f"📊 Monthly Summary — {month_start.strftime('%B %Y')}",
                    color=0x4ECDC4,
                )

                # Income & primary account
                if user.income_account_id:
                    primary = next((a for a in accounts if a.id == user.income_account_id), None)
                    if primary:
                        starting_balance = primary.current_balance + total_spent - income_deposited
                        embed.add_field(
                            name="⭐ Primary Account",
                            value=(
                                f"**{primary.bank_name} {primary.card_type}\n"
                                f"Start of month: ~${starting_balance:,.2f}\n"
                                f"Income deposited: +${income_deposited:,.2f}\n"
                                f"Current balance: **${primary.current_balance:,.2f}**"
                            ),
                            inline=False,
                        )

                embed.add_field(
                    name="💰 Spending",
                    value=(
                        f"Total: **${total_spent:,.2f}**\n"
                        f"Budget: ${monthly_budget:,.2f}\n"
                        f"{savings_text}"
                    ),
                    inline=True,
                )

                top_cat_text = (
                    f"{top_cat.icon} {top_cat.name}\n${float(top_cat.total):,.2f}"
                    if top_cat else "N/A"
                )
                top_card_text = (
                    f"{top_card.bank_name} {top_card.card_type}\n"
                    f"{top_card.count} purchases · ${float(top_card.total):,.2f}"
                    if top_card else "N/A"
                )
                embed.add_field(name="🏆 Top Category", value=top_cat_text, inline=True)
                embed.add_field(name="💳 Most Used Card", value=top_card_text, inline=True)

                # All account balances
                balance_lines = []
                for a in accounts:
                    marker = " ⭐" if a.id == user.income_account_id else ""
                    balance_lines.append(
                        f"{a.bank_name} {a.card_type}{marker}: "
                        f"**${a.current_balance:,.2f}**"
                    )
                embed.add_field(
                    name="🏦 All Balances",
                    value="\n".join(balance_lines) or "No accounts",
                    inline=False,
                )

                await channel.send(embed=embed)


    @app_commands.command(name="report", description="Generate a report on demand")
    @app_commands.describe(period="Report period")
    @app_commands.choices(period=[
        app_commands.Choice(name="Day", value="day"),
        app_commands.Choice(name="Week", value="week"),
        app_commands.Choice(name="Month", value="month"),
    ])
    async def report(self, interaction: discord.Interaction, period: app_commands.Choice[str]):
        await interaction.response.send_message(f"Generating **{period.name}** report...", ephemeral=True)
        channel = interaction.channel

        today = date.today()
        if period.value == "day":
            await self._send_daily_report(channel)
        elif period.value == "week":
            await self._send_weekly_report(channel)
        elif period.value == "month":
            await self._send_monthly_report(channel, today.year, today.month)


async def setup(bot: commands.Bot):
    await bot.add_cog(TasksCog(bot))
