import logging
from typing import Optional
import discord
from discord.ext import commands

from ..models import GuildConfig # For fetching notification_channel_id
# Corrected import path for generic CRUD functions
from ..core.crud_base_definitions import get_entity_by_id # To get GuildConfig
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
            if embed:
                await channel.send(message, embed=embed)
            else:
                await channel.send(message)
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

import json
from typing import Dict, Any # Make sure Dict and Any are imported if not already
from src.core.localization_utils import get_localized_message_template

async def parse_json_parameter(
    interaction: discord.Interaction,
    json_str: Optional[str],
    field_name: str,
    session: AsyncSession # For localization
) -> Optional[Dict[Any, Any]]:
    """
    Parses a JSON string parameter provided in a command.
    Sends a localized error message and returns None if parsing fails or string is empty.
    Returns the parsed dictionary on success, or an empty dict if json_str is None/empty.
    """
    if not json_str: # Handles None or empty string
        return {}

    try:
        parsed_json = json.loads(json_str)
        if not isinstance(parsed_json, dict):
            # Ensure guild_id is correctly passed, interaction.guild.id might be None if DM
            guild_id_for_loc = interaction.guild.id if interaction.guild else None
            error_msg_template = await get_localized_message_template(
                session,
                guild_id_for_loc, # Use potentially None guild_id
                "common:error_json_not_dict",
                str(interaction.locale),
                "JSON for field '{field_name}' must be a valid JSON object (e.g., {{key: value}})."
            )
            error_msg = error_msg_template.format(field_name=field_name)
            # Check if response has been deferred; if not, direct send might be needed
            # However, standard practice is to defer, so followup should be safe.
            await interaction.followup.send(error_msg, ephemeral=True)
            return None
        return parsed_json
    except json.JSONDecodeError as e:
        guild_id_for_loc = interaction.guild.id if interaction.guild else None
        error_msg_template = await get_localized_message_template(
            session,
            guild_id_for_loc,
            "common:error_invalid_json",
            str(interaction.locale),
            "Invalid JSON provided for field '{field_name}': {error_details}"
        )
        error_msg = error_msg_template.format(field_name=field_name, error_details=str(e))
        await interaction.followup.send(error_msg, ephemeral=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing JSON for field '{field_name}' in guild {interaction.guild_id if interaction.guild else 'DM'}: {e}", exc_info=True)
        guild_id_for_loc = interaction.guild.id if interaction.guild else None
        error_msg_template = await get_localized_message_template(
            session,
            guild_id_for_loc,
            "common:error_unexpected_json_parse",
            str(interaction.locale),
            "An unexpected error occurred while parsing JSON for field '{field_name}'."
        )
        error_msg = error_msg_template.format(field_name=field_name)
        await interaction.followup.send(error_msg, ephemeral=True)
        return None
