import logging
from typing import Optional, Union # Added Union
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

from typing import Tuple # Added for type hinting the tuple return

# Assuming Player model might be relevant, but for now, returning discord.User or Member
# from ..models.player import Player # If a Player model is needed for master_player
from ..models.guild import GuildConfig
from ..core.crud.crud_guild import guild_crud
from ..core.database import get_db_session
from ..core.localization_utils import get_localized_text # For error messages

logger = logging.getLogger(__name__)

async def get_master_player_from_interaction(
    interaction: discord.Interaction,
    session: AsyncSession # Keep session for potential future Player model fetching
) -> Optional[Union[discord.User, discord.Member]]: # Returns User/Member for now
    """
    Checks if the interacting user is an administrator.
    Placeholder: In future, this might fetch a Player object and check specific master roles.
    """
    if not interaction.guild: # Should not happen if called after guild check
        logger.warning("get_master_player_from_interaction called without guild context.")
        return None

    if interaction.user.guild_permissions.administrator:
        return interaction.user
    else:
        # This part might be redundant if ensure_guild_configured_and_get_session already handles permissions.
        # However, the original import suggested two separate functions.
        logger.warning(f"User {interaction.user.id} in guild {interaction.guild.id} is not an admin, but get_master_player_from_interaction was called.")
        # No message sent here, as the calling command should handle permission denial if this check is primary.
        return None


async def ensure_guild_configured_and_get_session(
    interaction: discord.Interaction
) -> Tuple[Optional[Union[discord.User, discord.Member]], Optional[AsyncSession]]:
    """
    Ensures the guild is configured for the bot and returns a master user object and a DB session.
    A "master user" is currently defined as a guild administrator.
    """
    if not interaction.guild or not interaction.guild_id:
        try:
            # Attempt to get localized message, fall back to default if session/localization fails early
            error_msg = "This command can only be used in a server."
            # Assuming no session or localization context available here yet for a more specific message.
            # error_msg = await get_localized_text("common:error_guild_only_command", str(interaction.locale), default="This command can only be used in a server.")
            await interaction.response.send_message(error_msg, ephemeral=True)
        except discord.errors.InteractionResponded:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error sending guild_only message: {e}")
        return None, None

    # Check for administrator permissions (basic "master" check)
    if not interaction.user.guild_permissions.administrator:
        try:
            # error_msg = await get_localized_text("common:error_admin_only_command", str(interaction.locale), default="You must be an administrator to use this command.")
            error_msg = "You must be an administrator to use this command."
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
        except discord.errors.InteractionResponded:
             await interaction.followup.send("You must be an administrator to use this command.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error sending admin_only message: {e}")
        return None, None # No session returned if user is not admin

    session: Optional[AsyncSession] = None
    try:
        session = await get_db_session().__aenter__() # Manually enter context for finer control

        guild_config = await guild_crud.get(session, id=interaction.guild_id)
        if not guild_config:
            logger.warning(f"GuildConfig not found for guild {interaction.guild_id}. Guild might not be initialized.")
            # error_msg = await get_localized_text("common:error_guild_not_configured", str(interaction.locale), default="This server is not configured for the bot. Please run initial setup.")
            error_msg = "This server is not configured for the bot. Please run initial setup."
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
            await session.close() # Close session as we are returning None for it
            return None, None

        # Add more specific checks for GuildConfig if needed, e.g., master_role_id, notification_channel_id
        # For now, just checking if it exists is the basic "configured" check.

        # If all checks pass, return the user (as master) and the session
        # The get_master_player_from_interaction function can be used here if more complex logic is needed
        # For now, admin check is sufficient.
        master_user = interaction.user # Simplified: admin user is the master user

        return master_user, session

    except Exception as e:
        logger.error(f"Error in ensure_guild_configured_and_get_session for guild {interaction.guild_id}: {e}", exc_info=True)
        # error_msg = await get_localized_text("common:error_unexpected_setup", str(interaction.locale), default="An unexpected error occurred during command setup.")
        error_msg = "An unexpected error occurred during command setup."
        if not interaction.response.is_done():
            try:
                await interaction.response.send_message(error_msg, ephemeral=True)
            except discord.errors.InteractionResponded:
                 await interaction.followup.send(error_msg, ephemeral=True)
        else:
            await interaction.followup.send(error_msg, ephemeral=True)

        if session:
            await session.close()
        return None, None
