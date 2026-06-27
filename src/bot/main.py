import asyncio
import logging

import discord
from discord.ext import commands
from sqlalchemy import select

from bot.config import DISCORD_CHANNEL_ID, DISCORD_TOKEN
from bot.database.models import RawMessage
from bot.database.session import async_session, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=" ", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"Bot connected as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Listening on channel ID: {DISCORD_CHANNEL_ID}")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
    except Exception:
        logger.exception("Failed to sync slash commands")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    try:
        async with async_session() as session:
            existing = await session.execute(
                select(RawMessage).where(RawMessage.discord_message_id == message.id)
            )
            if existing.scalar_one_or_none():
                return

            raw = RawMessage(
                discord_message_id=message.id,
                channel_id=message.channel.id,
                original_content=message.content,
            )
            session.add(raw)
            await session.commit()
            logger.info(f"Saved message {message.id} from {message.author}")
    except Exception:
        logger.exception(f"Failed to save message {message.id}")

    await bot.process_commands(message)


async def main():
    logger.info("Starting Finance Bot...")
    async with bot:
        await bot.load_extension("bot.cogs.setup")
        await bot.load_extension("bot.cogs.purchases")
        await bot.load_extension("bot.cogs.tasks")
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
