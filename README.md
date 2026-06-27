# Finance Bot

A Discord bot for personal expense tracking. Register purchases, manage recurring expenses, track account balances, and get automated daily, weekly, and monthly financial reports with charts.

## Features

- **Purchase tracking** — Register expenses and income with `/buy` and `/income`
- **Multiple accounts** — Track balances across debit and credit cards
- **Categories** — 13 built-in spending categories, add your own with `/add_category`
- **Recurring expenses** — Set up recurring payments with optional auto-registration and inter-account transfers
- **Biweekly income** — Automatic income deposits on the 15th and 30th of each month
- **Daily reports** — Spending summary per card, monthly budget progress with visual progress bar
- **Weekly reports** — Pie chart of spending by category, secondary account balances
- **Monthly reports** — Weekly spending timeline, category breakdown chart, savings analysis, most used card
- **On-demand reports** — `/report day|week|month` anytime

## Slash Commands

| Command | Description |
|---|---|
| `/setup` | Configure your profile (monthly income, savings goal) |
| `/add_account` | Add a bank account/card to track |
| `/buy` | Register a purchase |
| `/income` | Register an income |
| `/recurring` | Add a recurring expense or transfer |
| `/pay_recurring` | Pay a recurring expense with pre-filled data |
| `/add_category` | Add a new spending category |
| `/report` | Generate a report on demand (day, week, month) |

## Tech Stack

- Python 3.13, [uv](https://github.com/astral-sh/uv) for package management
- [discord.py](https://github.com/Rapptz/discord.py) for Discord integration
- SQLAlchemy async + Alembic for database migrations
- PostgreSQL with asyncpg driver
- matplotlib for chart generation

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL
- A Discord bot token ([Discord Developer Portal](https://discord.com/developers/applications))

### Environment Variables

Create a `.env` file:

```env
DISCORD_TOKEN=your_bot_token
DISCORD_CHANNEL_ID=your_channel_id
POSTGRES_PASSWORD=your_password
DATABASE_URL=postgres://postgres:your_password@localhost:5432/financebot
```

### Run Locally

```bash
uv sync
uv run alembic upgrade head
uv run python -m bot.main
```

### Run with Docker

```bash
docker compose up -d --build
```

This starts both PostgreSQL and the bot in an internal network. Migrations run automatically on startup.

## Project Structure

```
src/bot/
  config.py          # Environment variables
  main.py            # Bot client, on_message handler
  database/
    models.py        # SQLAlchemy models (7 tables)
    session.py       # Async engine and session factory
  cogs/
    setup.py         # /setup, /add_account
    purchases.py     # /buy, /income, /recurring, /pay_recurring, /add_category
    tasks.py         # Scheduled reports, auto-register, income deposits
alembic/             # Database migrations
```

## Database Schema

- **users** — Discord user profile, income, savings goal, primary account
- **accounts** — Bank accounts/cards with balances
- **balance_snapshots** — Balance history and income deposit tracking
- **categories** — Spending categories with optional budgets
- **purchases** — All transactions (expenses and income)
- **raw_messages** — Discord messages for future AI processing
- **recurring_expenses** — Recurring payments and inter-account transfers

## License

MIT
