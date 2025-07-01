import logging
import discord
from discord.ext import commands

from src.models import GuildConfig # For fetching notification_channel_id
from src.core.crud import get_entity_by_id # To get GuildConfig
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)

async def notify_master(
    bot: commands.Bot,
    session: AsyncSession, # DB session to fetch GuildConfig
    guild_id: int,
    message: str,
    embed: Optional[discord.Embed] = None
):
    """
    Sends a notification message to the guild's configured master notification channel.
    """
    if not guild_id:
        logger.warning("notify_master called without guild_id.")
        return

    guild_config = await get_entity_by_id(session, GuildConfig, entity_id=guild_id)

    if not guild_config or not guild_config.notification_channel_id:
        logger.warning(f"Guild {guild_id} has no notification channel configured or GuildConfig not found.")
        # Optionally, could try to DM the guild owner as a fallback if master_user_id is stored.
        return

    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.warning(f"Bot is not in guild {guild_id}, cannot send master notification.")
            return

        channel = guild.get_channel(guild_config.notification_channel_id)
        if isinstance(channel, discord.TextChannel): # Check if it's a text channel
            await channel.send(message, embed=embed)
            logger.info(f"Sent master notification to channel {channel.id} in guild {guild.id}: {message[:100]}")
        else:
            logger.warning(f"Notification channel {guild_config.notification_channel_id} in guild {guild_id} is not a valid text channel or not found.")
    except discord.Forbidden:
        logger.error(f"Bot lacks permissions to send message to channel {guild_config.notification_channel_id} in guild {guild_id}.")
    except discord.HTTPException as e:
        logger.error(f"Failed to send master notification to guild {guild_id} due to HTTP error: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending master notification to guild {guild_id}: {e}", exc_info=True)

# Example of how it might be called (from ai_orchestrator.py, after creating PendingGeneration):
# from src.bot.utils import notify_master
# from src.core.database import get_db_session # Assuming orchestrator has access to session factory
#
# async def some_orchestrator_function(bot_instance: commands.Bot, ...):
#     # ... logic ...
#     async with get_db_session() as session: # Orchestrator function should manage its own session for this
#          await notify_master(bot_instance, session, guild_id, "New content awaits moderation: ID X")
#     # ...
